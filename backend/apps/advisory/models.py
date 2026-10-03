"""Every question to the adviser and what the farmer was shown, for safety review."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class AdviceExchange(TimeStampedModel):
    case = models.ForeignKey("cases.Case", on_delete=models.CASCADE, related_name="advice")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    language = models.CharField(max_length=8)
    question = models.TextField()
    answer = models.TextField(help_text="What the farmer saw")
    raw_answer = models.TextField(blank=True, help_text="What the model wrote, if different")
    blocked = models.BooleanField(default=False, help_text="The automatic check replaced the answer")
    flags = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=64, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    latency_s = models.FloatField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["blocked", "created_at"])]

    def __str__(self):
        return f"Advice for case {self.case_id} ({self.language})"
