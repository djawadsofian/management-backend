from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Admins (role ADMIN or is_staff) can write, others read-only.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and (getattr(request.user, "role", None) == "ADMIN" or request.user.is_staff)

class IsProjectAssigneeOrAdmin(permissions.BasePermission):
    """
    Allows access if user is assigned to project or admin.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if getattr(request.user, "role", None) == "ADMIN" or request.user.is_staff:
            return True
        return request.user in obj.assigned_employers.all()