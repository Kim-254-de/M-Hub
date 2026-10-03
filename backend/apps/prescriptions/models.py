"""PLACEHOLDER (Documentation §9.2 `prescriptions`). Owned by Module 3 (Prescribe).

Module 4 reads prescriptions by code. Module 3 creates them after agrovet approval.
"""

import secrets

from django.db import models
from django.utils import timezone

from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.core.models import TimeStampedModel
from apps.products.models import Product

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
    approved_by = models.ForeignKey(Agrovet, on_delete=models.PROTECT, related_name="prescriptions")
    expires_at = models.DateTimeField()

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
