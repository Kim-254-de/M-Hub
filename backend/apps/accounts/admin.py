from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Farm, FarmerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("AgriSense", {"fields": ("phone", "role")}),)
    list_display = ("username", "phone", "role", "is_staff", "is_active")
    list_filter = BaseUserAdmin.list_filter + ("role",)
    search_fields = ("username", "phone", "first_name", "last_name")


@admin.register(FarmerProfile)
class FarmerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "county", "ward", "consent_at")
    list_filter = ("language", "county")
    search_fields = ("user__phone", "user__first_name", "ward")
    raw_id_fields = ("user",)


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("__str__", "farmer", "size_acres", "created_at")
    search_fields = ("name", "farmer__phone")
    raw_id_fields = ("farmer",)
