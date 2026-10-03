from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


def case_photo_upload_to(instance, filename):
    return f"cases/{instance.case_id}/{instance.id}_{filename}"


class Case(TimeStampedModel):
    """One crop problem reported by a farmer (Documentation §7).

    Minimal version owned by the Detect module; Diagnose reads from it.
    """

    class Status(models.TextChoices):
        REPORTED = "REPORTED"
        DIAGNOSING = "DIAGNOSING"
        SECOND_OPINION = "SECOND_OPINION"
        DIAGNOSED = "DIAGNOSED"
        UNKNOWN = "UNKNOWN"
        PRESCRIBED = "PRESCRIBED"
        EXPIRED = "EXPIRED"
        PURCHASED = "PURCHASED"
        VERIFIED = "VERIFIED"
        FLAGGED = "FLAGGED"

    class Channel(models.TextChoices):
        APP = "app"
        WHATSAPP = "whatsapp"

    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cases")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED, db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.APP)
    symptom_answers = models.JSONField(default=dict, blank=True)
    # Location where the photos were taken; sent to the diagnosis provider to improve accuracy.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["farmer", "-created_at"])]

    def __str__(self):
        return f"Case {self.id} ({self.status})"


class CasePhoto(TimeStampedModel):
    class Type(models.TextChoices):
        LEAF = "leaf"
        PLANT = "plant"
        STEM_FRUIT = "stem_fruit"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="photos")
    type = models.CharField(max_length=16, choices=Type.choices)
    image = models.ImageField(upload_to=case_photo_upload_to)

    class Meta(TimeStampedModel.Meta):
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.type} photo for case {self.case_id}"
