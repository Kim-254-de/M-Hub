"""D5 Products and Treatment Rules (Documentation §9.1, §9.2 `products`, `treatment_rules`).

Products mirror the PCPB register (Module 4 verifies labels against it).
Diseases and treatment rules drive the Prescribe rule filter (process 4.1).
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel
from apps.translations.catalog import language_chain

from .pcpb import parse_reg_no


class Product(TimeStampedModel):
    pcpb_reg_no = models.CharField(max_length=32, help_text='As printed, e.g. "PCPB (CR) 0856"')
    pcpb_key = models.CharField(max_length=32, unique=True, editable=False, help_text="Normalised lookup key")
    name = models.CharField(max_length=255)
    active_ingredients = models.JSONField(default=list, blank=True)
    approved_crops = models.JSONField(default=list, blank=True)
    label_rate = models.CharField(max_length=128, blank=True, help_text='As printed, e.g. "50 g per 20 L"')
    # Numeric label rate used for the dose calculation (process 4.3). Left empty, the
    # prescription tells the farmer to follow the label instead of giving a quantity.
    rate_per_acre = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Product per acre per spray"
    )
    rate_unit = models.CharField(max_length=4, choices=[("ml", "ml"), ("g", "g")], blank=True)
    pack_size = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Pack size, in rate_unit"
    )
    ppe_notes = models.TextField(blank=True, help_text="Safety notes shown on the prescription card")
    phi_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Pre-harvest interval")
    is_active = models.BooleanField(
        default=True, help_text="False if the registration is cancelled or expired"
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.pcpb_reg_no})"

    def clean(self):
        if not parse_reg_no(self.pcpb_reg_no):
            raise ValidationError({"pcpb_reg_no": 'Not a valid PCPB number, expected e.g. "PCPB (CR) 0856".'})

    def save(self, *args, **kwargs):
        key = parse_reg_no(self.pcpb_reg_no)
        if not key:
            raise ValidationError({"pcpb_reg_no": "Not a valid PCPB registration number."})
        self.pcpb_key = key
        super().save(*args, **kwargs)


class Disease(TimeStampedModel):
    """A tomato disease or pest an agrovet can confirm (D5)."""

    class Type(models.TextChoices):
        DISEASE = "disease"
        PEST = "pest"
        DISORDER = "disorder"

    name = models.CharField(max_length=128, unique=True)
    scientific_name = models.CharField(max_length=128, blank=True)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.DISEASE)
    # Diagnosis-provider entity ids (Kindwise suggestion ``id``) that mean this disease.
    # Names are matched too, so this is only needed when the provider's name differs.
    provider_ids = models.JSONField(default=list, blank=True)
    # Farmer-facing names by language code, e.g. {"sw": "..."}. Falls back to ``name``.
    local_names = models.JSONField(default=dict, blank=True)
    # Reviewed, product-free first steps shown while the farmer waits for an agrovet, by language
    # code: {"en": ["...", ...], "sw": [...]}. Empty: the general steps in diagnosis.messages are shown.
    safe_actions = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("name",)

    def __str__(self):
        return self.name

    def display_name(self, language: str) -> str:
        """The name in the first language the farmer reads (settings.LANGUAGE_FALLBACKS), else ``name``."""
        names = self.local_names or {}
        return next((names[lang] for lang in language_chain(language) if names.get(lang)), self.name)

    def actions_for(self, language: str) -> list[str]:
        """Reviewed steps in the farmer's language only; callers fall back to general steps they can read."""
        return (self.safe_actions or {}).get(language) or []


class TreatmentRule(TimeStampedModel):
    """Disease -> recommended active ingredient for a crop (§9.2 `treatment_rules`).

    A product is allowed for a disease when it is registered for the crop and
    contains one of the rule's active ingredients.
    """

    disease = models.ForeignKey(Disease, on_delete=models.CASCADE, related_name="treatment_rules")
    active_ingredient = models.CharField(max_length=128)
    crop = models.CharField(max_length=32, default="tomato")

    class Meta(TimeStampedModel.Meta):
        ordering = ("disease", "active_ingredient")
        constraints = [
            models.UniqueConstraint(
                fields=["disease", "active_ingredient", "crop"], name="products_unique_treatment_rule"
            ),
        ]

    def __str__(self):
        return f"{self.disease}: {self.active_ingredient} ({self.crop})"
