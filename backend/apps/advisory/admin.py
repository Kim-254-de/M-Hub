from django.contrib import admin

from .models import AdviceExchange


@admin.register(AdviceExchange)
class AdviceExchangeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "case", "language", "blocked", "model")
    list_filter = ("blocked", "language", "model")
    search_fields = ("question", "answer", "raw_answer")
    readonly_fields = [f.name for f in AdviceExchange._meta.fields]

    def has_add_permission(self, request):
        return False
