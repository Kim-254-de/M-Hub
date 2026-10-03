from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


def case_photo_upload_to(instance, filename):
    return f"cases/{instance.case_id}/{instance.id}_{filename}"


def case_voice_note_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"
    return f"cases/{instance.id}/voice_note.{extension}"


class Case(TimeStampedModel):
    """One crop problem reported by a farmer (Documentation §7).

    Owned by the Detect module; Diagnose reads from it.
    """

    class Status(models.TextChoices):
        # Detect: farmer is still adding photos and answers. Nothing has been sent anywhere.
        DRAFT = "DRAFT"
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
    farm = models.ForeignKey(
        "accounts.Farm", on_delete=models.PROTECT, related_name="cases", null=True, blank=True
    )
    # Detect creates cases as DRAFT explicitly; the REPORTED default keeps other creators unchanged.
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
    # Copied from the farmer's profile at submission, so area statistics and outbreak
    # alerts stay correct if the farmer later moves.
    county = models.CharField(max_length=64, blank=True)
    ward = models.CharField(max_length=64, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Optional spoken description from the farmer, for the reviewing agrovet.
    voice_note = models.FileField(upload_to=case_voice_note_upload_to, null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["farmer", "-created_at"]),
            models.Index(fields=["ward", "submitted_at"]),
        ]

    def __str__(self):
        return f"Case {self.id} ({self.status})"


class CasePhoto(TimeStampedModel):
    class Type(models.TextChoices):
        LEAF = "leaf"
        PLANT = "plant"
        STEM_FRUIT = "stem_fruit"

    REQUIRED_TYPES = (Type.LEAF, Type.PLANT, Type.STEM_FRUIT)

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="photos")
    type = models.CharField(max_length=16, choices=Type.choices)
    image = models.ImageField(upload_to=case_photo_upload_to)
    # Local quality measurements taken at upload (see cases.quality). Kept for threshold tuning.
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sharpness = models.FloatField(null=True, blank=True)
    brightness = models.FloatField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("created_at",)
        constraints = [
            # A retake replaces the earlier photo of the same type.
            models.UniqueConstraint(fields=["case", "type"], name="cases_one_photo_per_type"),
        ]

    def __str__(self):
        return f"{self.type} photo for case {self.case_id}"
