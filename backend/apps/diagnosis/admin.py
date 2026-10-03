from django.contrib import admin

from .models import AIDiagnosis, AISuggestion


class AISuggestionInline(admin.TabularInline):
    model = AISuggestion
    extra = 0
    can_delete = False
    fields = ("rank", "name", "scientific_name", "probability", "is_healthy", "external_id")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AIDiagnosis)
class AIDiagnosisAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "provider", "status", "is_plant", "is_tomato", "attempts", "created_at")
    list_filter = ("status", "provider", "error_code")
    search_fields = ("id", "case__id", "external_ref")
    raw_id_fields = ("case",)
    readonly_fields = [f.name for f in AIDiagnosis._meta.fields]
    inlines = [AISuggestionInline]

    def has_add_permission(self, request):
        return False
