# apps/core/permissions.py
"""
Centralized permission classes for the entire application.
Consolidates all permission logic to avoid duplication.
"""
from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """
    Permission class for admin-only access.
    Grants access to superusers and users with ADMIN role.
    """
    message = "Only administrators can perform this action."

    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and (request.user.is_superuser or request.user.role == 'ADMIN')
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows:
    - Read access (GET, HEAD, OPTIONS) for authenticated users
    - Write access (POST, PUT, PATCH, DELETE) only for admins
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        return (
            request.user 
            and request.user.is_authenticated 
            and (request.user.is_superuser or request.user.role == 'ADMIN')
        )


class IsAdminOrAssistant(permissions.BasePermission):
    """
    Permission for admin or assistant roles.
    Used for management operations that assistants can also perform.
    """
    message = "Only administrators or assistants can perform this action."

    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and request.user.role in ['ADMIN', 'ASSISTANT']
        )


class IsProjectAssignee(permissions.BasePermission):
    """
    Object-level permission for project assignees.
    Grants access if user is assigned to the project or is an admin.
    """
    message = "You must be assigned to this project to access it."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # Admins can access everything
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        
        # Check if user is assigned to the project
        return obj.assigned_employers.filter(id=request.user.id).exists()


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission for resource owners.
    Grants access to the creator of a resource or admins.
    """
    message = "You must be the owner or an administrator."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # Admins can access everything
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        
        # Check if user is the creator
        return hasattr(obj, 'created_by') and obj.created_by == request.user