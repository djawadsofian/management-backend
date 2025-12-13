# apps/stock/views.py
"""
Refactored ProductViewSet using mixins and cleaner structure.
Removed redundant code and improved organization.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import F

from apps.core.mixins import (
    StandardFilterMixin,
    TimestampOrderingMixin,
)
from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdminOrAssistant
from .models import Product
from .serializers import ProductSerializer
from .services import StockService


class ProductViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    viewsets.ModelViewSet
):
    """
    ViewSet for managing products.
    
    Permissions:
        - List/Retrieve: Authenticated users
        - Create/Update/Delete: Admins only
    
    Endpoints:
        - GET /api/stock/products/ - List all products
        - POST /api/stock/products/ - Create product (admin)
        - GET /api/stock/products/{id}/ - Retrieve product
        - PUT/PATCH /api/stock/products/{id}/ - Update product (admin)
        - DELETE /api/stock/products/{id}/ - Delete product (admin)
        - GET /api/stock/products/low-stock/ - List low stock products
        - POST /api/stock/products/{id}/adjust-stock/ - Adjust stock (admin)
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = StaticPagination
    permission_classes =[IsAdminOrAssistant]
    
    # Filter/Search/Order configuration
    filterset_fields = ['sku', 'unit']
    search_fields = ['name', 'sku']
    ordering_fields = ['name', 'quantity', 'reorder_threshold', 'buying_price', 'selling_price' ,'created_at', 'updated_at']
    ordering = ['-created_at']

  

    @action(detail=False, methods=['get'], url_path='low-stock')
    def low_stock(self, request):
        """
        Get products with low stock levels.
        
        Query params:
            - threshold: Optional custom threshold
        """
        threshold = request.query_params.get('threshold')
        
        if threshold:
            queryset = Product.objects.filter(quantity__lte=int(threshold))
        else:
            queryset = Product.objects.filter(quantity__lte=F('reorder_threshold'))
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='out-of-stock')
    def out_of_stock(self, request):
        """Get products that are completely out of stock"""
        queryset = StockService.get_out_of_stock_products()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='adjust-stock')
    def adjust_stock(self, request, pk=None):
        """
        Manually adjust stock for a product.
        
        Request body:
            {
                "quantity": 10,
                "operation": "add"  // or "subtract"
            }
        """
        product = self.get_object()
        quantity = request.data.get('quantity')
        operation = request.data.get('operation', 'add')
        
        if not quantity:
            return Response(
                {'message': 'Quantité requise'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            updated_product = StockService.adjust_stock(
                product,
                quantity,
                operation
            )
            serializer = self.get_serializer(updated_product)
            return Response(serializer.data)
        
        except Exception as e:
            return Response(
                {'message': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        

    def list(self, request, *args, **kwargs):
        # Get the original response
        response = super().list(request, *args, **kwargs)
        
        # Calculate totals for the current filtered queryset
        queryset = self.filter_queryset(self.get_queryset())
        
        # Calculate totals
        from django.db.models import F, Sum
        
        totals = queryset.aggregate(
            total_buying_price=Sum(F('quantity') * F('buying_price')),
            total_selling_price=Sum(F('quantity') * F('selling_price'))
        )
        
        # Add totals to response data
        response.data['total_buying_price'] = totals['total_buying_price'] or 0
        response.data['total_selling_price'] = totals['total_selling_price'] or 0
        
        return response