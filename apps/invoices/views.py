# apps/invoices/views.py
"""
Refactored invoice views with better organization and error handling.
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
    InvoiceLineSerializer
)


class InvoiceViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    SetCreatedByMixin,
    AdminWritePermissionMixin,
    viewsets.ModelViewSet
):
    """
    ViewSet for managing invoices.
    
    Permissions:
        - List/Retrieve: Authenticated users
        - Create/Update/Delete: Admins only
    
    Custom Actions:
        - issue: Issue a draft invoice
        - mark_paid: Mark invoice as paid
        - cancel: Cancel invoice
        - add_line: Add line item to invoice
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
        return InvoiceSerializer

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def issue(self, request, pk=None):
        """
        Issue a draft invoice (change status to ISSUED).
        Validates that invoice can be issued before changing status.
        """
        invoice = self.get_object()
        
        try:
            invoice.issue()
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def mark_paid(self, request, pk=None):
        """Mark invoice as paid"""
        invoice = self.get_object()
        
        try:
            invoice.mark_paid()
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """Cancel invoice"""
        invoice = self.get_object()
        
        try:
            invoice.cancel()
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def add_line(self, request, pk=None):
        """
        Add a line item to an invoice.
        
        Request body:
            {
                "product": 1,
                "quantity": 5,
                "unit_price": 100.00,
                "discount": 10.00
            }
        """
        invoice = self.get_object()
        serializer = InvoiceLineSerializer(data=request.data)
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


class InvoiceLineViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing invoice line items.
    Nested under invoices: /api/invoices/{invoice_id}/lines/
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

    @transaction.atomic
    def perform_create(self, serializer):
        """Create line item and associate with invoice"""
        invoice_id = self.kwargs.get('invoice_pk')
        invoice = get_object_or_404(Invoice, id=invoice_id)
        serializer.save(invoice=invoice)

    @transaction.atomic
    def perform_update(self, serializer):
        """Update line item and recalculate invoice total"""
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        """Delete line item and recalculate invoice total"""
        instance.delete()