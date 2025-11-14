# apps/invoices/views.py
"""
Strict invoice views with controlled stock management.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.core.mixins import (
    StandardFilterMixin,
    TimestampOrderingMixin,
    SetCreatedByMixin,
    AdminWritePermissionMixin
)
from apps.core.pagination import StaticPagination
from .models import Invoice, InvoiceLine
from .serializers import (
    InvoiceSerializer,
    InvoiceCreateSerializer,
    InvoiceUpdateSerializer,
    InvoiceLineSerializer,
    InvoiceStatusUpdateSerializer
)


class InvoiceViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    SetCreatedByMixin,
    AdminWritePermissionMixin,
    viewsets.ModelViewSet
):
    """
    ViewSet for managing invoices with strict stock control.
    
    Permissions:
        - List/Retrieve: Authenticated users
        - Create/Update/Delete: Admins only
    
    Custom Actions:
        - update_status: Change invoice status (issue/mark_paid/revert_to_draft)
        - add_line: Add line item to invoice
        
    Status Flow:
        - DRAFT: Can edit, stock NOT affected
        - ISSUED: Can edit, stock IS affected  
        - PAID: Cannot edit, stock remains affected
    """
    queryset = Invoice.objects.select_related(
        'project', 'project__client', 'created_by'
    ).prefetch_related('lines', 'lines__product')
    
    pagination_class = StaticPagination
    
    # Filtering configuration
    filterset_fields = ['status', 'project', 'created_by']
    search_fields = [
        'bon_de_commande', 'bon_de_versement',
        'bon_de_reception', 'facture', 'project__name'
    ]
    ordering_fields = ['issued_date', 'due_date', 'total', 'created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return InvoiceUpdateSerializer
        elif self.action == 'update_status':
            return InvoiceStatusUpdateSerializer
        return InvoiceSerializer

    def perform_destroy(self, instance):
        """
        Override destroy to ensure stock is restored if needed.
        The model's delete() method handles stock restoration.
        """
        if not instance.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete a paid invoice")
        
        instance.delete()

    @action(detail=True, methods=['post'], url_path='update-status')
    @transaction.atomic
    def update_status(self, request, pk=None):
        """
        Update invoice status with proper stock management.
        
        Request body:
            {
                "action": "issue" | "mark_paid" | "revert_to_draft"
            }
        
        Status Transitions:
            - issue: DRAFT -> ISSUED (affects stock)
            - mark_paid: ISSUED -> PAID (locks invoice)
            - revert_to_draft: ISSUED -> DRAFT (restores stock)
        """
        invoice = self.get_object()
        
        serializer = InvoiceStatusUpdateSerializer(
            data=request.data,
            context={'invoice': invoice}
        )
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        
        try:
            if action_type == 'issue':
                invoice.issue()
                message = "Invoice issued successfully. Stock has been deducted."
                
            elif action_type == 'mark_paid':
                invoice.mark_paid()
                message = "Invoice marked as paid. No more edits allowed."
                
            elif action_type == 'revert_to_draft':
                invoice.revert_to_draft()
                message = "Invoice reverted to draft. Stock has been restored."
            
            return Response({
                'message': message,
                'invoice': InvoiceSerializer(invoice).data
            })
            
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='add-line')
    @transaction.atomic
    def add_line(self, request, pk=None):
        """
        Add a line item to an invoice.
        
        - DRAFT: Line added, no stock change
        - ISSUED: Line added, stock deducted immediately
        - PAID: Not allowed
        
        Request body:
            {
                "product": 1,
                "quantity": 5,
                "unit_price": 100.00,
                "discount": 10.00
            }
        """
        invoice = self.get_object()
        
        if not invoice.is_editable:
            return Response(
                {'detail': 'Cannot add lines to a paid invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = InvoiceLineSerializer(
            data=request.data,
            context={'invoice': invoice}
        )
        serializer.is_valid(raise_exception=True)
        
        try:
            line = serializer.save(invoice=invoice)
            return Response(
                InvoiceLineSerializer(line).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        

    @action(detail=True, methods=['post'], url_path='add-lines')
    @transaction.atomic
    def add_lines(self, request, pk=None):
        """
        Add multiple line items to an invoice in bulk.
        
        Request body:
            [
                {
                    "product": 1,
                    "quantity": 5,
                    "unit_price": 100.00,
                    "discount": 10.00
                },
                {
                    "product": 2, 
                    "quantity": 2,
                    "unit_price": 50.00,
                    "discount": 0.00
                }
            ]
        """
        invoice = self.get_object()
        
        if not invoice.is_editable:
            return Response(
                {'detail': 'Cannot add lines to a paid invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lines_data = request.data
        if not isinstance(lines_data, list):
            return Response(
                {'detail': 'Expected a list of line items'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_lines = []
        errors = []
        
        for index, line_data in enumerate(lines_data):
            serializer = InvoiceLineSerializer(
                data=line_data,
                context={'invoice': invoice}
            )
            
            if serializer.is_valid():
                try:
                    line = serializer.save(invoice=invoice)
                    created_lines.append(line)
                except Exception as e:
                    errors.append(f"Line {index + 1}: {str(e)}")
            else:
                errors.append(f"Line {index + 1}: {serializer.errors}")
        
        if errors:
            # If any errors occurred, rollback the transaction
            transaction.set_rollback(True)
            return Response(
                {'detail': 'Some lines could not be created', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Recalculate totals once for all lines
        invoice.calculate_totals()
        
        return Response(
            InvoiceLineSerializer(created_lines, many=True).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'], url_path='can-issue')
    def can_issue(self, request, pk=None):
        """
        Check if invoice can be issued.
        Returns validation status and any error messages.
        """
        invoice = self.get_object()
        can_issue, message = invoice.can_be_issued()
        
        return Response({
            'can_issue': can_issue,
            'message': message,
            'current_status': invoice.status,
            'line_count': invoice.lines.count(),
            'total': float(invoice.total)
        })


class InvoiceLineViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing invoice line items.
    Nested under invoices: /api/invoices/{invoice_id}/lines/
    
    Stock behavior depends on parent invoice status:
    - DRAFT: No stock changes
    - ISSUED: Stock adjusted on create/update/delete
    - PAID: No modifications allowed
    """
    queryset = InvoiceLine.objects.select_related('invoice', 'product')
    serializer_class = InvoiceLineSerializer
    pagination_class = StaticPagination

    def get_permissions(self):
        from apps.core.permissions import IsAdmin
        return [IsAdmin()]

    def get_queryset(self):
        """Filter lines by invoice if invoice_pk is provided"""
        queryset = super().get_queryset()
        invoice_id = self.kwargs.get('invoice_pk')
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        return queryset

    def get_serializer_context(self):
        """Add invoice to serializer context"""
        context = super().get_serializer_context()
        invoice_id = self.kwargs.get('invoice_pk')
        if invoice_id:
            try:
                context['invoice'] = Invoice.objects.get(id=invoice_id)
            except Invoice.DoesNotExist:
                pass
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        """Create line item and associate with invoice"""
        invoice_id = self.kwargs.get('invoice_pk')
        invoice = get_object_or_404(Invoice, id=invoice_id)
        
        if not invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot add lines to a paid invoice")
        
        serializer.save(invoice=invoice)

    @transaction.atomic
    def perform_update(self, serializer):
        """Update line item"""
        if not serializer.instance.invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot update lines on a paid invoice")
        
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        """Delete line item"""
        if not instance.invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete lines from a paid invoice")
        
        instance.delete()