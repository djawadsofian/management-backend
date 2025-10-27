# apps/core/mixins.py
"""
Reusable mixins for ViewSets to reduce code duplication.
These mixins provide common functionality across different ViewSets.
"""
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend


class StandardFilterMixin:
    """
    Provides standard filtering, searching, and ordering configuration.
    Apply this to ViewSets that need these features.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    

class TimestampOrderingMixin:
    """
    Provides default ordering by creation date (newest first).
    """
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


class SetCreatedByMixin:
    """
    Automatically sets the created_by field to the current user.
    Use in ViewSets where objects have a created_by field.
    """
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminWritePermissionMixin:
    """
    Provides permission logic where:
    - List/Retrieve: Any authenticated user
    - Write operations: Admin only
    """
    def get_permissions(self):
        from apps.core.permissions import IsAdmin
        from rest_framework.permissions import IsAuthenticated
        
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdmin()]


class SoftDeleteMixin:
    """
    Provides soft delete functionality.
    Override destroy to mark as deleted instead of actually deleting.
    """
    def perform_destroy(self, instance):
        if hasattr(instance, 'is_deleted'):
            instance.is_deleted = True
            instance.save(update_fields=['is_deleted'])
        else:
            super().perform_destroy(instance)