from apps.core.pagination import StaticPagination
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend


from .models import Client
from .serializers import ClientSerializer
from apps.core.permissions import IsAdmin

class ClientViewSet(viewsets.ModelViewSet):

    queryset = Client.objects.all().order_by('-created_at')
    serializer_class = ClientSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    pagination_class = StaticPagination
    filterset_fields = ['email']
    search_fields = ['name', 'email', 'phone_number']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdmin()]

