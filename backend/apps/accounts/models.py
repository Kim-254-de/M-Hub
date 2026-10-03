import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


def default_crops():
    return ["tomato"]


class User(AbstractUser):
    """Platform user. Farmer and agrovet profiles hang off this model.

    Defined at project start so AUTH_USER_MODEL never has to be swapped later.
    """

    class Role(models.TextChoices):
        FARMER = "farmer", "Farmer"
        AGROVET = "agrovet", "Agrovet"
        ADMIN = "admin", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FARMER)

    def __str__(self):
        return self.get_full_name() or self.username


class FarmerProfile(TimeStampedModel):
    """Farmer details used across modules (Documentation §9.2 ``farmers``)."""

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        SWAHILI = "sw", "Kiswahili"
        KIKUYU = "ki", "Gĩkũyũ"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="farmer_profile")
    language = models.CharField(max_length=8, choices=Language.choices, default=Language.SWAHILI)
    county = models.CharField(max_length=64, blank=True)
    # IEBC constituency name; see apps.accounts.locations.
    sub_county = models.CharField(max_length=64, blank=True)
    ward = models.CharField(max_length=64, blank=True, db_index=True)
    # Data-use consent (Kenya Data Protection Act, 2019). Registration fails without it.
    consent_at = models.DateTimeField()
    # Updated through apps.rewards.services.adjust_trust; weights peer input in Diagnose.
    trust_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # SMS updates about the farmer's cases (the app's notifications switch). Sign-up codes always go.
    notifications_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Farmer profile for {self.user}"


class Farm(TimeStampedModel):
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="farms")
    name = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    # Used by Prescribe for dose calculation.
    size_acres = models.DecimalField(
        max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    crops = models.JSONField(default=default_crops)

    def __str__(self):
        return self.name or f"Farm {self.id}"
