from django.contrib import admin

from .models import Disease, Product, TreatmentRule


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "pcpb_reg_no", "is_active", "phi_days")
    list_filter = ("is_active",)
    search_fields = ("name", "pcpb_reg_no", "pcpb_key")
    readonly_fields = ("pcpb_key",)


class TreatmentRuleInline(admin.TabularInline):
    model = TreatmentRule
    extra = 1


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "scientific_name", "type", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("name", "scientific_name")
    inlines = [TreatmentRuleInline]
