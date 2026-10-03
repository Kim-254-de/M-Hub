from django.conf import settings
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


class AgrovetReview(TimeStampedModel):
    """A case assigned to a verified agrovet for confirmation (process 3.4) or a second opinion (3.6)."""

    class Round(models.IntegerChoices):
        FIRST = 1
        SECOND_OPINION = 2

    class Status(models.TextChoices):
        PENDING = "pending"
        DECIDED = "decided"
        # Not answered in time, or the farmer picked another agrovet; the case was reassigned.
        WITHDRAWN = "withdrawn"

    class Decision(models.TextChoices):
        DISEASE = "disease"  # confirmed or corrected to ``disease``
        UNSURE = "unsure"  # cannot tell from the evidence

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="agrovet_reviews")
    agrovet = models.ForeignKey("agrovets.Agrovet", on_delete=models.PROTECT, related_name="reviews")
    round = models.PositiveSmallIntegerField(choices=Round.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    chosen_by_farmer = models.BooleanField(default=False)
    decision = models.CharField(max_length=16, choices=Decision.choices, blank=True)
    disease = models.ForeignKey(
        "products.Disease", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True)
    # Evidence as the agrovet saw it when deciding: AI opinion, similar-case majority, peer summary.
    evidence = models.JSONField(default=dict, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            # One open review per case; one review per agrovet per case (second opinions need someone new).
            models.UniqueConstraint(
                fields=["case"], condition=Q(status="pending"), name="diagnosis_one_pending_review_per_case"
            ),
            models.UniqueConstraint(fields=["case", "agrovet"], name="diagnosis_one_review_per_agrovet"),
        ]
        indexes = [models.Index(fields=["agrovet", "status", "-created_at"])]

    def __str__(self):
        return f"Review round {self.round} of case {self.case_id} by {self.agrovet_id} ({self.status})"


class PeerComment(TimeStampedModel):
    """Optional input from a trusted nearby farmer while a case waits (process 3.3)."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="peer_comments")
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="peer_comments"
    )
    disease = models.ForeignKey(
        "products.Disease", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    comment = models.CharField(max_length=500, blank=True)
    # The farmer's trust-based weight when they commented.
    weight = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["case", "farmer"], name="diagnosis_one_peer_comment_per_farmer"),
        ]

    def __str__(self):
        return f"Peer comment on case {self.case_id}"


class FinalDiagnosis(TimeStampedModel):
    """The human-confirmed diagnosis of a case (§9.2 `diagnoses` with ``is_final``).

    Every final diagnosis is labelled local data: it feeds similar-case search (3.2).
    """

    class Confidence(models.TextChoices):
        HIGH = "high"  # agrovet agrees with AI and similar cases
        MEDIUM = "medium"  # agrovet agrees with one other source, or a second agrovet
        LOW = "low"  # agrovet only; no other evidence to compare with

    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="final_diagnosis")
    disease = models.ForeignKey("products.Disease", on_delete=models.PROTECT, related_name="final_diagnoses")
    confidence = models.CharField(max_length=8, choices=Confidence.choices)
    confirmed_by = models.ForeignKey(
        "agrovets.Agrovet", on_delete=models.PROTECT, related_name="final_diagnoses"
    )
    # Copied from the case so similar-case search does not need joins.
    ward = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "final diagnoses"
        indexes = [
            models.Index(fields=["disease", "-created_at"]),
            models.Index(fields=["ward", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.disease} for case {self.case_id} ({self.confidence})"
