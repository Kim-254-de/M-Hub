from django.contrib import admin

from .models import Conversation, InboundMessage, OutboundMessage


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("phone", "user", "step", "last_inbound_at", "updated_at")
    search_fields = ("phone", "user__first_name", "profile_name")
    raw_id_fields = ("user",)
    readonly_fields = ("last_inbound_at", "created_at", "updated_at")


@admin.register(InboundMessage)
class InboundMessageAdmin(admin.ModelAdmin):
    list_display = ("phone", "kind", "text", "reply_id", "status", "attempts", "created_at")
    list_filter = ("status", "kind")
    search_fields = ("phone", "wamid", "text")
    readonly_fields = [f.name for f in InboundMessage._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(OutboundMessage)
class OutboundMessageAdmin(admin.ModelAdmin):
    list_display = ("phone", "source_ref", "status", "attempts", "created_at")
    list_filter = ("status",)
    search_fields = ("phone", "source_ref", "provider_message_id")
    readonly_fields = [f.name for f in OutboundMessage._meta.fields]

    def has_add_permission(self, request):
        return False
