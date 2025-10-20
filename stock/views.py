from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product
from django.db import models
from .serializers import ProductSerializer
from .permissions import IsAdminRole

class ProductViewSet(viewsets.ModelViewSet):
    """
    List & retrieve: authenticated users.
    Create/Update/Delete: Admin only.
    """
    queryset = Product.objects.all().order_by('name')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['sku', 'unit']
    search_fields = ['name', 'sku']
    ordering_fields = [
        'name', 'quantity', 'reorder_threshold', 
        'buying_price', 'selling_price'  # Added new ordering fields
    ]
    ordering = ['name']

    def get_permissions(self):
        # read-only actions allowed for any authenticated user
        if self.action in ['list', 'retrieve', 'low_stock']:
            return [IsAuthenticated()]
        # write actions are admin-only
        return [IsAdminRole()]

    @action(detail=False, methods=['get'], url_path='low-stock', url_name='low_stock')
    def low_stock(self, request):
        """
        Returns products with quantity <= reorder_threshold.
        """
        qs = self.get_queryset().filter(quantity__lte= models.F('reorder_threshold'))
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)