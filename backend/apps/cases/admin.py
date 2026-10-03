from django.contrib import admin

from .models import Case, CasePhoto


class CasePhotoInline(admin.TabularInline):
    model = CasePhoto
    extra = 0
    readonly_fields = ("width", "height", "sharpness", "brightness")


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("id", "farmer", "status", "channel", "ward", "created_at", "submitted_at")
    list_filter = ("status", "channel", "county")
    search_fields = ("id", "farmer__username", "farmer__phone", "ward")
    raw_id_fields = ("farmer", "farm")
    inlines = [CasePhotoInline]
