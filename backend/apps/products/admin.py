from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "pcpb_reg_no", "is_active", "phi_days")
    list_filter = ("is_active",)
    search_fields = ("name", "pcpb_reg_no", "pcpb_key")
    readonly_fields = ("pcpb_key",)
