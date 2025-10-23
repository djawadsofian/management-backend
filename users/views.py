from django.shortcuts import render
from common.pagination import DynamicPagination
from rest_framework import viewsets
from .models import CustomUser
from .serializers import UserSerializer, EmployerCreateSerializer, AssistantCreateSerializer
from .permissions import IsAdmin, IsAdminOrAssistant
from rest_framework.permissions import IsAuthenticated

class EmployerViewSet(viewsets.ModelViewSet):
    """
    Admin-only endpoints to manage employer accounts.
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_EMPLOYER)
    permission_classes = [IsAdminOrAssistant]  # Updated to allow assistants
    pagination_class = DynamicPagination
    def get_serializer_class(self):
        if self.action == 'create':
            return EmployerCreateSerializer
        return UserSerializer

class AssistantViewSet(viewsets.ModelViewSet):
    """
    Admin-only endpoints to manage assistant accounts.
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_ASSISTANT)
    permission_classes = [IsAdmin]  # Only admins can manage assistants
    pagination_class = DynamicPagination
    def get_serializer_class(self):
        if self.action == 'create':
            return AssistantCreateSerializer
        return UserSerializer

