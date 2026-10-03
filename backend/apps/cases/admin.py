from django.contrib import admin

from .models import Case, CasePhoto


class CasePhotoInline(admin.TabularInline):
    model = CasePhoto
    extra = 0


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("id", "farmer", "status", "channel", "created_at")
    list_filter = ("status", "channel")
    search_fields = ("id", "farmer__username", "farmer__phone")
    raw_id_fields = ("farmer",)
    inlines = [CasePhotoInline]
