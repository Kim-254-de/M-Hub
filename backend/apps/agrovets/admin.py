from django.contrib import admin

from .models import Agrovet, StoreItem


class StoreItemInline(admin.TabularInline):
    model = StoreItem
    extra = 0
    raw_id_fields = ("product",)


@admin.register(Agrovet)
class AgrovetAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "pcpb_licence_no", "has_qualified_staff", "trust_score")
    list_filter = ("status", "has_qualified_staff")
    search_fields = ("name", "pcpb_licence_no", "user__username", "phone")
    raw_id_fields = ("user",)
    inlines = [StoreItemInline]
