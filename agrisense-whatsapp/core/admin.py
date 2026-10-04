from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from whatsapp import notify

from .models import Agrovet, Diagnosis, Farmer, Order, Product

admin.site.site_header = "AgriSense Hub admin"
admin.site.site_title = "AgriSense Hub"


@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "county", "ward", "language", "points", "is_registered", "created_at")
    list_filter = ("is_registered", "county", "language")
    search_fields = ("full_name", "phone", "whatsapp_name", "ward")


class ProductInline(admin.TabularInline):
    model = Product
    extra = 0
    fields = ("name", "pcpb_reg_no", "pack_size", "price", "farmer_discount_pct", "target_keywords", "crops",
              "in_stock")


@admin.register(Agrovet)
class AgrovetAdmin(admin.ModelAdmin):
    list_display = ("name", "town", "county", "phone", "is_verified")
    list_filter = ("is_verified", "county")
    search_fields = ("name", "town", "phone")
    inlines = [ProductInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "pcpb_reg_no", "pack_size", "agrovet", "price", "farmer_discount_pct", "in_stock")
    list_filter = ("in_stock", "agrovet__county", "agrovet")
    search_fields = ("name", "pcpb_reg_no", "active_ingredient", "target_keywords")


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ("id", "farmer", "crop", "disease", "confidence_pct", "status", "outcome", "created_at")
    list_filter = ("status", "outcome", "crop", "farmer__county")
    search_fields = ("disease", "farmer__full_name", "farmer__phone")
    readonly_fields = ("photo", "confidence", "raw_response", "created_at", "wa_media_id")
    fields = ("farmer", "crop", "photo", "disease", "confidence", "description", "treatment", "status",
              "reviewed_by", "agrovet_note", "outcome", "outcome_verified", "wa_media_id", "raw_response",
              "created_at")

    @admin.display(description="Confidence")
    def confidence_pct(self, obj):
        return f"{round(obj.confidence * 100)}%"

    @admin.display(description="Photo")
    def photo(self, obj):
        if not obj.image:
            return "-"
        return format_html('<img src="{}" style="max-width:320px;border-radius:8px">', obj.image.url)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        reviewed = (Diagnosis.STATUS_CONFIRMED, Diagnosis.STATUS_REJECTED)
        if change and "status" in form.changed_data and obj.status in reviewed:
            notify.diagnosis_reviewed(obj)
            self.message_user(request, "The farmer has been notified on WhatsApp.", messages.SUCCESS)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "farmer", "product", "quantity", "amount", "status", "label_result", "mpesa_receipt",
                    "pickup_code", "created_at")
    list_filter = ("status", "label_result", "product__agrovet")
    search_fields = ("farmer__phone", "farmer__full_name", "mpesa_receipt", "pickup_code")
    readonly_fields = ("checkout_request_id", "mpesa_receipt", "paid_at", "collected_at", "label_result",
                       "label_reg_no", "created_at")
    actions = ["mark_collected"]

    @admin.action(description="Mark selected orders as collected")
    def mark_collected(self, request, queryset):
        n = 0
        for order in queryset.filter(status=Order.STATUS_PAID).select_related("farmer", "product__agrovet"):
            order.status, order.collected_at = Order.STATUS_COLLECTED, timezone.now()
            order.save(update_fields=["status", "collected_at"])
            notify.ask_label_photo(order)
            n += 1
        self.message_user(request, f"{n} order(s) marked as collected.")
