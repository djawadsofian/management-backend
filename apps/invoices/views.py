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
from apps.core.permissions import IsAdminOrAssistant  # Add this import
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
        - Create/Update/Delete: Admins and Assistants only
    
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
    filterset_fields = ['status', 'project', 'created_by','facture']
    search_fields = [
        'bon_de_commande', 'bon_de_versement',
        'bon_de_reception', 'facture', 'project__name',
        'project__client__name',  # Client name
        'project__client__address__province',  # Client province
        'project__client__address__city',  # Client city
        'project__client__address__postal_code',  # Client postal code
    ]
    ordering_fields = ['issued_date', 'due_date', 'total', 'created_at']

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        
        # Handle multiple city filter
        cities = self.request.query_params.getlist('city')
        if cities:
            queryset = queryset.filter(project__client__address__city__in=cities)
        
        return queryset

    def get_permissions(self):
        """Allow admins and assistants to modify, authenticated users to read"""
        if self.action in ['list', 'retrieve', 'can_issue']:
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return [IsAdminOrAssistant()]  # Updated to include assistants

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
            raise ValidationError({"message": "Impossible de supprimer une facture payée"})
        
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
        
        if not serializer.is_valid():
            return Response(
                {"message": "Données de requête invalides"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        action_type = serializer.validated_data['action']
        
        try:
            if action_type == 'issue':
                invoice.issue()
                message = "Facture émise avec succès. Stock déduit."
                
            elif action_type == 'mark_paid':
                invoice.mark_paid()
                message = "Facture marquée comme payée. Aucune modification autorisée."
                
            elif action_type == 'revert_to_draft':
                invoice.revert_to_draft()
                message = "Facture revenue au brouillon. Stock restauré."
            
            return Response({
                'message': message,
                'invoice': InvoiceSerializer(invoice).data
            })
            
        except Exception as e:
            return Response(

                {"message": str(e)},
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
                {"message": "Impossible d'ajouter des lignes à une facture payée"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = InvoiceLineSerializer(
            data=request.data,
            context={'invoice': invoice}
        )
        
        if not serializer.is_valid():
            # Convert serializer errors to French message format
            error_message = self._get_serializer_error_message(serializer.errors)
            return Response(
                {"message": error_message},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            line = serializer.save(invoice=invoice)
            return Response(
                InvoiceLineSerializer(line).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de l'ajout de la ligne: {str(e)}"},
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
                {"message": "Impossible d'ajouter des lignes à une facture payée"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lines_data = request.data
        if not isinstance(lines_data, list):
            return Response(
                {"message": "Données attendues: une liste d'articles"},
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
                    errors.append(f"Ligne {index + 1}: {str(e)}")
            else:
                error_message = self._get_serializer_error_message(serializer.errors)
                errors.append(f"Ligne {index + 1}: {error_message}")
        
        if errors:
            # If any errors occurred, rollback the transaction
            transaction.set_rollback(True)
            return Response(
                {"message": "Certaines lignes n'ont pas pu être créées", "errors": errors},
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

    def _get_serializer_error_message(self, errors):
        """
        Convert serializer errors to French message format.
        """
        if 'message' in errors:
            return str(errors['message'])
        
        # Get first error and convert to French
        for field, field_errors in errors.items():
            if isinstance(field_errors, list):
                error_text = str(field_errors[0])
            else:
                error_text = str(field_errors)
            
            # Translate common validation errors to French
            if 'required' in error_text.lower():
                return f"Champ {field} obligatoire manquant"
            elif 'invalid' in error_text.lower():
                return f"Donnée invalide pour {field}"
            elif 'not exist' in error_text.lower():
                return f"{field} n'existe pas"
            elif 'positive' in error_text.lower():
                return f"{field} doit être positif"
            elif 'negative' in error_text.lower():
                return f"{field} ne peut pas être négatif"
            else:
                return error_text
        
        return "Données invalides"


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
        """Allow admins and assistants to modify"""
        return [IsAdminOrAssistant()]  # Updated to include assistants

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

    def handle_exception(self, exc):
        """Override to return French error messages"""
        from rest_framework.views import exception_handler
        response = exception_handler(exc, self)
        
        if response is not None:
            if hasattr(exc, 'detail'):
                if isinstance(exc.detail, dict) and 'message' in exc.detail:
                    response.data = exc.detail
                else:
                    response.data = {"message": str(exc.detail)}
            else:
                response.data = {"message": str(exc)}
        
        return response

    @transaction.atomic
    def perform_create(self, serializer):
        """Create line item and associate with invoice"""
        invoice_id = self.kwargs.get('invoice_pk')
        invoice = get_object_or_404(Invoice, id=invoice_id)
        
        if not invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"message": "Impossible d'ajouter des lignes à une facture payée"})
        
        serializer.save(invoice=invoice)

    @transaction.atomic
    def perform_update(self, serializer):
        """Update line item"""
        if not serializer.instance.invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"message": "Impossible de modifier les lignes d'une facture payée"})
        
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        """Delete line item"""
        if not instance.invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"message": "Impossible de supprimer les lignes d'une facture payée"})
        
        instance.delete()