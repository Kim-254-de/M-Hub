"""PLACEHOLDER (Documentation §9.2 `products`). Owned by the Prescribe / register-sync work.

Built so Module 4 can verify purchases against the PCPB register. Field names
follow §9.2; replace or extend freely, keeping `pcpb_key` lookups working.
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel

from .pcpb import parse_reg_no


class Product(TimeStampedModel):
    pcpb_reg_no = models.CharField(max_length=32, help_text='As printed, e.g. "PCPB (CR) 0856"')
    pcpb_key = models.CharField(max_length=32, unique=True, editable=False, help_text="Normalised lookup key")
    name = models.CharField(max_length=255)
    active_ingredients = models.JSONField(default=list, blank=True)
    approved_crops = models.JSONField(default=list, blank=True)
    label_rate = models.CharField(max_length=128, blank=True)
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
