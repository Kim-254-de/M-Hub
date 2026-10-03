from django.contrib import admin

from .models import CheckIn, SprayRecord


class CheckInInline(admin.TabularInline):
    model = CheckIn
    extra = 0
    fields = ("day", "new_spots", "share_affected", "photo", "notes", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SprayRecord)
class SprayRecordAdmin(admin.ModelAdmin):
    list_display = ("case", "product", "disease", "ward", "sprayed_at", "completed_at")
    list_filter = ("disease", "product")
    search_fields = ("case__id", "ward")
    raw_id_fields = ("case", "order", "farmer", "product", "disease")
    inlines = [CheckInInline]
