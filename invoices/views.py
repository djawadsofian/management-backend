# invoices/views.py
from common.pagination import StaticPagination
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Invoice, InvoiceLine
from .serializers import (
    InvoiceSerializer, InvoiceCreateSerializer, 
    InvoiceUpdateSerializer, InvoiceLineSerializer
)
from stock.permissions import IsAdminRole


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related(
        'project', 'project__client', 'created_by'
    ).prefetch_related('lines', 'lines__product').order_by('-created_at')
    
    filter_backends = [DjangoFilterBackend]
    pagination_class = StaticPagination
    filterset_fields = ['status', 'project', 'created_by']
    search_fields = [
        'bon_de_commande', 'bon_de_versement', 
        'bon_de_reception', 'facture', 'project__name'
    ]
    ordering_fields = ['issued_date', 'due_date', 'total', 'created_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return InvoiceUpdateSerializer
        return InvoiceSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminRole()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def add_line(self, request, pk=None):
        """Add a line item to an invoice"""
        invoice = self.get_object()
        serializer = InvoiceLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            line = serializer.save(invoice=invoice)
            invoice.calculate_total()
            
        return Response(InvoiceLineSerializer(line).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update invoice status"""
        invoice = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Invoice.STATUS_CHOICES):
            return Response(
                {'detail': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        invoice.status = new_status
        invoice.save()
        
        return Response({'detail': 'Status updated successfully'})


class InvoiceLineViewSet(viewsets.ModelViewSet):
    queryset = InvoiceLine.objects.select_related('invoice', 'product')
    serializer_class = InvoiceLineSerializer
    permission_classes = [IsAdminRole]  # Only admins can manage lines directly
    pagination_class = StaticPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        invoice_id = self.kwargs.get('invoice_pk')
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        return queryset

    def perform_create(self, serializer):
        invoice_id = self.kwargs.get('invoice_pk')
        invoice = get_object_or_404(Invoice, id=invoice_id)
        
        with transaction.atomic():
            line = serializer.save(invoice=invoice)
            invoice.calculate_total()

    def perform_update(self, serializer):
        with transaction.atomic():
            line = serializer.save()
            line.invoice.calculate_total()

    def perform_destroy(self, instance):
        invoice = instance.invoice
        with transaction.atomic():
            instance.delete()
            invoice.calculate_total()
