from rest_framework.permissions import BasePermission


class CanAccessCase(BasePermission):
    """The case's farmer, or staff.

    Agrovet access is granted per assigned case once agrovet review (process 3.4) exists.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or obj.farmer_id == user.id))
