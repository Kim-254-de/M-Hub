from django.contrib import admin

from .models import Prescription, TreatmentOutcome


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("code", "case", "disease", "approved_product", "approved_by", "expires_at")
    search_fields = ("code", "case__id")
    raw_id_fields = ("case", "approved_product", "approved_by", "disease")
    filter_horizontal = ("allowed_products",)
    readonly_fields = ("code",)


@admin.register(TreatmentOutcome)
class TreatmentOutcomeAdmin(admin.ModelAdmin):
    list_display = ("case", "disease", "product", "improved", "ward", "created_at")
    list_filter = ("improved", "disease")
    raw_id_fields = ("case", "farmer", "disease", "product")
