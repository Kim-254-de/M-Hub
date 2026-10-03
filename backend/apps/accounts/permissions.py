from rest_framework.permissions import BasePermission

from .models import User


class IsFarmer(BasePermission):
    message = "Only farmer accounts can do this."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.FARMER)
