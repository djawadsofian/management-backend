# apps/supplier/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q, Count
from django.db import transaction
from django.utils import timezone
from django.db import models 

from apps.core.mixins import StandardFilterMixin, TimestampOrderingMixin
from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdminOrAssistant
from .models import Supplier, Debt
from .serializers import (
    SupplierSerializer, SupplierDetailSerializer,
    DebtSerializer, DebtCreateSerializer, PaymentSerializer
)


class SupplierViewSet(StandardFilterMixin, TimestampOrderingMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing suppliers and their debt information.
    """
    queryset = Supplier.objects.prefetch_related('debts')
    pagination_class = StaticPagination
    permission_classes = [IsAdminOrAssistant]
    
    # Filter/Search/Order configuration
    filterset_fields = ['is_active', 'city', 'wilaya']
    search_fields = ['name', 'company', 'email', 'phone', 'tax_id']
    ordering_fields = ['name', 'company', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Override to annotate with calculated fields for better performance"""
        queryset = super().get_queryset()
        
        # Always annotate with debt statistics for better performance
        queryset = queryset.annotate(
            annotated_debt_count=Count('debts'),
            annotated_total_debt=Sum('debts__total_price'),
            annotated_total_paid=Sum('debts__paid_price'),
            annotated_paid_debt_count=Count('debts', filter=Q(
                debts__paid_price=models.F('debts__total_price')
            )),
            annotated_pending_debt_count=Count('debts', filter=Q(
                debts__paid_price__lt=models.F('debts__total_price')
            ))
        )
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SupplierDetailSerializer
        return SupplierSerializer

    @action(detail=True, methods=['get'])
    def debts(self, request, pk=None):
        """Get all debts for a specific supplier"""
        supplier = self.get_object()
        debts = supplier.debts.all()
        
        # Apply filtering
        status_filter = request.query_params.get('status')
        if status_filter == 'paid':
            debts = debts.filter(is_paid=True)
        elif status_filter == 'pending':
            debts = debts.filter(is_paid=False)
        elif status_filter == 'overdue':
            debts = debts.filter(is_paid=False, due_date__lt=timezone.now().date())
        
        # Handle ordering - FIX: remove remaining_amount from ordering_fields
        ordering = request.query_params.get('ordering', '')
        if ordering in ['remaining_amount', '-remaining_amount']:
            # For API consistency, we'll sort by total_price instead
            if ordering == 'remaining_amount':
                debts = debts.order_by('total_price')
            else:
                debts = debts.order_by('-total_price')
        elif ordering:
            debts = debts.order_by(ordering)
        else:
            debts = debts.order_by('-date')
        
        # Paginate and return
        page = self.paginate_queryset(debts)
        if page is not None:
            serializer = DebtSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = DebtSerializer(debts, many=True)
        return Response(serializer.data)
# In apps/supplier/views.py - update the debt_summary method

    @action(detail=False, methods=['get'], url_path='debt-summary')
    def debt_summary(self, request):
        """
        Get debt summary for all suppliers.
        """
        # Aggregate totals using database fields only
        summary = Debt.objects.aggregate(
            total_debt_amount=Sum('total_price'),
            total_paid_amount=Sum('paid_price'),
            total_debts=Count('id'),
            paid_debts=Count('id', filter=Q(is_paid=True)),
            pending_debts=Count('id', filter=Q(is_paid=False))
        )
        
        total_debt = summary['total_debt_amount'] or 0
        total_paid = summary['total_paid_amount'] or 0
        remaining_amount = total_debt - total_paid
        
        # Count suppliers with outstanding debts
        suppliers_with_debts = Supplier.objects.filter(
            debts__is_paid=False
        ).distinct().count()

        # FIX: Count suppliers with ONLY paid debts (no pending debts)
        fully_paid_suppliers = Supplier.objects.annotate(
            has_pending_debts=Count('debts', filter=Q(debts__is_paid=False)),
            has_paid_debts=Count('debts', filter=Q(debts__is_paid=True))
        ).filter(
            has_pending_debts=0,  # No pending debts
            has_paid_debts__gt=0  # Has at least one paid debt
        ).count()

        return Response({
            'total_debt_amount': total_debt,
            'total_paid_amount': total_paid,
            'total_remaining_amount': remaining_amount,
            'supplier_count': Supplier.objects.count(),
            'suppliers_with_outstanding_debts': suppliers_with_debts,
            'summary_by_status': {
                'fully_paid_suppliers': fully_paid_suppliers,
                'has_pending_debts': suppliers_with_debts,
                'no_debts': Supplier.objects.filter(debts__isnull=True).count()  # Suppliers with no debts at all
            }
        })

    @action(detail=False, methods=['get'], url_path='outstanding-debts')
    def outstanding_debts(self, request):
        """Get suppliers with outstanding debts"""
        # Get suppliers with pending debts
        supplier_ids_with_pending_debts = Debt.objects.filter(
            is_paid=False
        ).values_list('supplier_id', flat=True).distinct()
        
        suppliers = self.get_queryset().filter(
            id__in=supplier_ids_with_pending_debts
        )
        
        # Filter by minimum remaining amount if provided
        min_remaining = request.query_params.get('min_remaining')
        if min_remaining:
            try:
                min_remaining = float(min_remaining)
                # We have to do this filtering in Python since it's a property
                suppliers = [
                    supplier for supplier in suppliers 
                    if supplier.total_remaining_amount >= min_remaining
                ]
            except ValueError:
                pass
        
        page = self.paginate_queryset(suppliers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(suppliers, many=True)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """Override list to handle calculated field ordering"""
        # Remove problematic ordering parameters
        ordering = request.query_params.get('ordering', '')
        if ordering in ['remaining_amount', '-remaining_amount', 'total_debt_amount', '-total_debt_amount']:
            # Use the annotated queryset from get_queryset
            pass
        
        return super().list(request, *args, **kwargs)


class DebtViewSet(StandardFilterMixin, TimestampOrderingMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing supplier debts.
    """
    queryset = Debt.objects.select_related('supplier')
    pagination_class = StaticPagination
    permission_classes = [IsAdminOrAssistant]
    
    # Filter/Search/Order configuration - FIX: remove remaining_amount
    filterset_fields = ['is_paid', 'supplier', 'date', 'due_date']
    search_fields = ['description', 'supplier__name', 'reference_number']
    ordering_fields = ['date', 'due_date', 'total_price', 'paid_price']  # Removed remaining_amount
    ordering = ['-date']

    def get_serializer_class(self):
        if self.action == 'create':
            return DebtCreateSerializer
        return DebtSerializer

    def get_queryset(self):
        """Override to handle calculated field ordering"""
        queryset = super().get_queryset()
        
        ordering = self.request.query_params.get('ordering', '')
        if ordering in ['remaining_amount', '-remaining_amount']:
            # We can't order by property in database, so order by the components
            if ordering == 'remaining_amount':
                queryset = queryset.order_by('total_price', '-paid_price')
            else:
                queryset = queryset.order_by('-total_price', 'paid_price')
        
        return queryset

    @action(detail=True, methods=['post'], url_path='add-payment')
    @transaction.atomic
    def add_payment(self, request, pk=None):
        """
        Add a payment to a debt.
        """
        debt = self.get_object()
        
        serializer = PaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"message": "Données de requête invalides"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        amount = serializer.validated_data['amount']
        
        try:
            debt.add_payment(amount)
            return Response({
                'message': f"Paiement de {amount} ajouté avec succès",
                'debt': DebtSerializer(debt).data
            })
        except ValueError as e:
            return Response(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='mark-paid')
    @transaction.atomic
    def mark_paid(self, request, pk=None):
        """Mark debt as fully paid"""
        debt = self.get_object()
        
        try:
            debt.mark_as_paid()
            return Response({
                'message': "Dette marquée comme payée",
                'debt': DebtSerializer(debt).data
            })
        except Exception as e:
            return Response(
                {"message": f"Erreur: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], url_path='overdue')
    def overdue_debts(self, request):
        """Get all overdue debts"""
        overdue_debts = self.get_queryset().filter(
            is_paid=False,
            due_date__lt=timezone.now().date()
        )
        
        page = self.paginate_queryset(overdue_debts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(overdue_debts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='summary')
    def debt_summary(self, request):
        """Get overall debt summary"""
        summary = Debt.objects.aggregate(
            total_debt_amount=Sum('total_price'),
            total_paid_amount=Sum('paid_price'),
            total_debts=Count('id'),
            paid_debts=Count('id', filter=Q(is_paid=True)),
            pending_debts=Count('id', filter=Q(is_paid=False))
        )
        
        total_debt = summary['total_debt_amount'] or 0
        total_paid = summary['total_paid_amount'] or 0
        remaining = total_debt - total_paid
        
        return Response({
            'total_debt_amount': total_debt,
            'total_paid_amount': total_paid,
            'total_remaining_amount': remaining,
            'debt_count': {
                'total': summary['total_debts'],
                'paid': summary['paid_debts'],
                'pending': summary['pending_debts']
            }
        })