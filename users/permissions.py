from rest_framework import permissions

class IsAdmin(permissions.BasePermission):
    """
    Allows access only to users with role ADMIN (or Django superuser).
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'ADMIN'))

class IsAdminOrAssistant(permissions.BasePermission):
    """
    Allows access to users with role ADMIN or ASSISTANT.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) in ['ADMIN', 'ASSISTANT']))

class IsAssistant(permissions.BasePermission):
    """
    Allows access only to users with role ASSISTANT.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'role', None) == 'ASSISTANT')