"""D6 Prescriptions (Documentation §6.3, §9.2 `prescriptions`).

Module 3 (Prescribe) creates a prescription when the agrovet approves it; Module 4
reads it by code. A prescription only exists once approved, so its code is always valid.
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.core.models import TimeStampedModel
from apps.products.models import Disease, Product

# No 0/O/1/I so codes survive being read aloud or typed from a printed card.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    return "AGR-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class Prescription(TimeStampedModel):
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="prescriptions")
    code = models.CharField(max_length=16, unique=True, default=generate_code, editable=False)
    allowed_products = models.ManyToManyField(Product, related_name="allowed_in_prescriptions")
    approved_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_in_prescriptions"
    )
    quantity = models.CharField(max_length=128, blank=True, help_text='Dose for the farm, e.g. "2 x 250 ml"')
    # The same dose as numbers, so the farmer's card and SMS can say it in their language.
    # Empty amount: no numeric label rate or farm size, so the farmer follows the label.
    dose_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dose_unit = models.CharField(max_length=4, blank=True)
    dose_packs = models.PositiveSmallIntegerField(null=True, blank=True)
    dose_pack_size = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    approved_by = models.ForeignKey(Agrovet, on_delete=models.PROTECT, related_name="prescriptions")
    expires_at = models.DateTimeField()
    disease = models.ForeignKey(
        Disease, on_delete=models.PROTECT, null=True, blank=True, related_name="prescriptions"
    )
    # The ranked options as the agrovet saw them (4.2), kept to monitor prescribing patterns.
    ranking = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.code

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def purchasable_product_ids(self) -> set:
        """Products that satisfy this prescription: the approved one or any allowed option."""
        ids = set(self.allowed_products.values_list("id", flat=True))
        if self.approved_product_id:
            ids.add(self.approved_product_id)
        return ids


class TreatmentOutcome(TimeStampedModel):
    """A farmer's report of whether a product worked (Documentation §14, Phase 2 follow-up).

    Feeds the local-evidence ranking in Prescribe (4.2). Only outcomes from verified
    purchases count as evidence (§11), so each one is tied to a verified case.
    """

    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="treatment_outcome")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    disease = models.ForeignKey(Disease, on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="outcomes")
    # From the farmer's final (day 7) follow-up: the spread has stopped and the crop is no worse.
    improved = models.BooleanField()
    # First follow-up day on which the farmer reported the spread stopping (None if it never did).
    days_after_spraying = models.PositiveSmallIntegerField(null=True, blank=True)
    # Copied from the case so evidence search does not need joins.
    ward = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["disease", "product", "-created_at"])]

    def __str__(self):
        return f"{self.product} for {self.disease}: {'improved' if self.improved else 'no improvement'}"
