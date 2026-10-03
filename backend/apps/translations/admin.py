from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from . import catalog
from .models import Translation


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    list_display = ("key", "language", "status", "is_current", "is_safety", "translated_by", "reviewed_by")
    list_filter = ("language", "status")
    search_fields = ("key", "text")
    fields = ("key", "language", "english", "text", "translated_by", "status", "reviewed_by", "reviewed_at")
    readonly_fields = ("english", "status", "reviewed_by", "reviewed_at")
    actions = ["approve"]

    @admin.display(description="English (current)")
    def english(self, obj):
        source = obj.source if obj and obj.pk else None
        return source.english if source else "-"

    @admin.display(boolean=True, description="Current")
    def is_current(self, obj):
        return obj.is_current

    @admin.display(boolean=True, description="Safety")
    def is_safety(self, obj):
        source = obj.source
        return bool(source and source.safety)

    def save_model(self, request, obj, form, change):
        # Saved text is a translation of today's English.
        source = catalog.get_source(obj.key)
        if source is not None:
            obj.source_text = source.english
        super().save_model(request, obj, form, change)

    def has_approve_permission(self, request):
        return request.user.has_perm("translations.approve_translation")

    @admin.action(description="Approve selected translations (shown to farmers)", permissions=["approve"])
    def approve(self, request, queryset):
        approved = 0
        for translation in queryset:
            try:
                translation.approve(request.user)
                approved += 1
            except ValidationError as exc:
                self.message_user(request, f"{translation}: {' '.join(exc.messages)}", messages.ERROR)
        if approved:
            self.message_user(request, f"Approved {approved} translation(s).", messages.SUCCESS)
