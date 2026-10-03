from django.contrib import admin
from django.utils import timezone

from .models import Order, Payment, StoreFlag, Verification


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ("status", "amount_kes", "phone", "mpesa_receipt", "result_code", "result_desc", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class VerificationInline(admin.TabularInline):
    model = Verification
    extra = 0
    can_delete = False
    fields = ("type", "result", "product", "detected_reg_no", "actor", "photo", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "farmer",
        "agrovet",
        "product",
        "total_kes",
        "payment_method",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_method")
    search_fields = ("id", "prescription__code", "farmer__phone", "agrovet__name")
    readonly_fields = [f.name for f in Order._meta.fields]
    inlines = [PaymentInline, VerificationInline]

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "amount_kes", "phone", "status", "mpesa_receipt", "created_at")
    list_filter = ("status",)
    search_fields = ("mpesa_receipt", "checkout_request_id", "phone", "order__id")
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "type", "result", "detected_reg_no", "created_at")
    list_filter = ("type", "result")
    search_fields = ("order__id", "detected_reg_no")
    readonly_fields = [f.name for f in Verification._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(StoreFlag)
class StoreFlagAdmin(admin.ModelAdmin):
    list_display = ("agrovet", "failed_checks", "reason", "created_at", "resolved_at")
    list_filter = ("resolved_at",)
    search_fields = ("agrovet__name",)
    readonly_fields = ("agrovet", "failed_checks", "reason", "created_at")
    actions = ["resolve"]

    @admin.action(description="Mark selected flags as resolved")
    def resolve(self, request, queryset):
        queryset.filter(resolved_at__isnull=True).update(resolved_at=timezone.now())
