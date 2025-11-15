from django_filters import rest_framework as filters
from rest_framework import viewsets, filters as drf_filters
from rest_framework.permissions import IsAuthenticated
from apps.core.pagination import StaticPagination
from .models import Client
from .serializers import ClientSerializer
from apps.core.permissions import IsAdmin


class ClientFilter(filters.FilterSet):
    """Custom filter for Client with JSONField support"""
    province = filters.CharFilter(field_name='address__province', lookup_expr='iexact')
    city = filters.CharFilter(field_name='address__city', lookup_expr='icontains')
    postal_code = filters.CharFilter(field_name='address__postal_code')
    
    class Meta:
        model = Client
        fields = ['email', 'is_corporate', 'province', 'city', 'postal_code']


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('-created_at')
    serializer_class = ClientSerializer
    filter_backends = [filters.DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = ClientFilter  # Use custom filter class
    pagination_class = StaticPagination
    search_fields = [
    'name', 
    'email', 
    'phone_number',
    'address__province',    # Search in province
    'address__city',        # Search in city  
    'address__postal_code', # Search in postal code
    'address__street',      # Search in street (if you have this field)
    ]   
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        
        # Handle multiple city filter
        cities = self.request.query_params.getlist('city')
        if cities:
            queryset = queryset.filter(address__city__in=cities)
        
        return queryset

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdmin()]