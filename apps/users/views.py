# apps/users/views.py
"""
Refactored user management views.
Simplified by removing redundant code and using proper mixins.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdmin, IsAdminOrAssistant
from apps.core.mixins import StandardFilterMixin
from .models import CustomUser
from .serializers import (
    UserSerializer,
    EmployerCreateSerializer,
    AssistantCreateSerializer
)


class BaseUserViewSet(StandardFilterMixin, viewsets.ModelViewSet):
    """
    Base ViewSet for user management with common configuration.
    """
    pagination_class = StaticPagination
    filterset_fields = ['role', 'is_active', 'wilaya', 'group']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering_fields = ['username', 'email', 'date_joined']
    ordering = ['username']

    def get_serializer_class(self):
        """Use appropriate serializer for create vs other actions"""
        if self.action == 'create':
            return self.create_serializer_class
        return UserSerializer


class EmployerViewSet(BaseUserViewSet):
    """
    ViewSet for managing employer accounts.
    
    Permissions:
        - Admins and Assistants can manage employers
    
    Endpoints:
        - GET /api/employers/ - List employers
        - POST /api/employers/ - Create employer
        - GET /api/employers/{id}/ - Retrieve employer
        - PUT/PATCH /api/employers/{id}/ - Update employer
        - DELETE /api/employers/{id}/ - Delete employer
        - POST /api/employers/{id}/deactivate/ - Deactivate employer
        - POST /api/employers/{id}/activate/ - Activate employer
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_EMPLOYER)
    permission_classes = [IsAdminOrAssistant]
    create_serializer_class = EmployerCreateSerializer

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an employer account"""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate an employer account"""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        serializer = self.get_serializer(user)
        return Response(serializer.data)


class AssistantViewSet(BaseUserViewSet):
    """
    ViewSet for managing assistant accounts.
    
    Permissions:
        - Only admins can manage assistants
    
    Endpoints:
        - GET /api/assistants/ - List assistants
        - POST /api/assistants/ - Create assistant
        - GET /api/assistants/{id}/ - Retrieve assistant
        - PUT/PATCH /api/assistants/{id}/ - Update assistant
        - DELETE /api/assistants/{id}/ - Delete assistant
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_ASSISTANT)
    permission_classes = [IsAdmin]
    create_serializer_class = AssistantCreateSerializer