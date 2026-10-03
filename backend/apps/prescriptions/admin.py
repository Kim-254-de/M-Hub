from django.contrib import admin

from .models import Prescription


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("code", "case", "approved_product", "approved_by", "expires_at")
    search_fields = ("code", "case__id")
    raw_id_fields = ("case", "approved_product", "approved_by")
    filter_horizontal = ("allowed_products",)
    readonly_fields = ("code",)
