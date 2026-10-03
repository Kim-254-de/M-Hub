from django.contrib import admin

from .models import SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ("to", "purpose", "status", "provider_status", "attempts", "created_at", "delivered_at")
    list_filter = ("status", "purpose")
    search_fields = ("to", "source_ref", "provider_message_id")
    readonly_fields = [f.name for f in SmsMessage._meta.fields]

    def has_add_permission(self, request):
        return False
