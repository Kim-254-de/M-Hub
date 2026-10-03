from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanAccessCase(BasePermission):
    """The case's farmer, or staff. An agrovet reviewing the case may read it."""

    def has_object_permission(self, request, view, obj):
        from .review import agrovet_can_view_case

        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_staff or obj.farmer_id == user.id:
            return True
        return request.method in SAFE_METHODS and agrovet_can_view_case(user, obj)
