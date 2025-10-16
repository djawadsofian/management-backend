from rest_framework import permissions

class IsAdminRole(permissions.BasePermission):
    """
    Allows access only to users with role ADMIN or superusers.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'ADMIN'))
