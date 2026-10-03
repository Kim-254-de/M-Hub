from django.db import models
from django.db.models import Q

from apps.cases.models import Case
from apps.core.models import TimeStampedModel


class AIDiagnosis(TimeStampedModel):
    """One AI identification run for a case (Documentation §8.3, process 3.1).

    The AI only suggests. A verified agrovet makes the final diagnosis.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="ai_diagnoses")
    provider = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    # Provider output
    external_ref = models.CharField(max_length=64, blank=True, help_text="Provider identification id")
    model_version = models.CharField(max_length=64, blank=True)
    is_plant_probability = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    crop_name = models.CharField(max_length=128, blank=True)
    crop_probability = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)

    # Interpretation of the output, used by Detect (retake prompt) and the agreement check.
    is_plant = models.BooleanField(null=True)
    is_tomato = models.BooleanField(null=True)

    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "AI diagnosis"
        verbose_name_plural = "AI diagnoses"
        constraints = [
            # At most one run in flight per case, so credits are never spent twice concurrently.
            models.UniqueConstraint(
                fields=["case"],
                condition=Q(status__in=["PENDING", "PROCESSING"]),
                name="diagnosis_one_active_ai_run_per_case",
            ),
        ]
        indexes = [models.Index(fields=["case", "-created_at"])]

    def __str__(self):
        return f"AI diagnosis {self.id} for case {self.case_id} ({self.status})"

    @property
    def needs_retake(self) -> bool:
        """True when the photos do not show a plant, or clearly not a tomato."""
        return self.status == self.Status.COMPLETED and (self.is_plant is False or self.is_tomato is False)

    @property
    def top_suggestion(self):
        return self.suggestions.order_by("rank").first()


class AISuggestion(models.Model):
    """One ranked disease/pest/healthy suggestion from the provider."""

    ai_diagnosis = models.ForeignKey(AIDiagnosis, on_delete=models.CASCADE, related_name="suggestions")
    rank = models.PositiveSmallIntegerField()
    external_id = models.CharField(max_length=64, help_text="Provider entity id; stable over time")
    name = models.CharField(max_length=255)
    scientific_name = models.CharField(max_length=255, blank=True)
    probability = models.DecimalField(max_digits=5, decimal_places=4)
    is_healthy = models.BooleanField(default=False)
    details = models.JSONField(default=dict, blank=True)
    similar_images = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("ai_diagnosis", "rank")
        constraints = [
            models.UniqueConstraint(fields=["ai_diagnosis", "rank"], name="diagnosis_unique_suggestion_rank"),
        ]
        indexes = [models.Index(fields=["external_id"])]

    def __str__(self):
        return f"#{self.rank} {self.name} ({self.probability})"
