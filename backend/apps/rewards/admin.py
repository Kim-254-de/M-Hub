from django.contrib import admin

from .models import RewardEntry, TrustEvent


@admin.register(RewardEntry)
class RewardEntryAdmin(admin.ModelAdmin):
    list_display = ("farmer", "reason", "points", "source_ref", "created_at")
    list_filter = ("reason",)
    search_fields = ("farmer__username", "farmer__phone", "source_ref")
    raw_id_fields = ("farmer",)
    readonly_fields = ("farmer", "reason", "points", "source_ref", "created_at")


@admin.register(TrustEvent)
class TrustEventAdmin(admin.ModelAdmin):
    list_display = ("user", "reason", "delta", "source_ref", "created_at")
    list_filter = ("reason",)
    search_fields = ("user__username", "user__phone", "source_ref")
    raw_id_fields = ("user",)
    readonly_fields = ("user", "reason", "delta", "source_ref", "created_at")
