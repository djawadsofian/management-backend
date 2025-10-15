from rest_framework import permissions

class IsAdmin(permissions.BasePermission):
    """
    Allows access only to users with role ADMIN (or Django superuser).
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'ADMIN'))
