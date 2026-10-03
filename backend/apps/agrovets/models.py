"""PLACEHOLDER (Documentation §9.2 `agrovets`, `store_items`). May be replaced by the agrovet onboarding work.

Field names follow §9.2. Location is stored as latitude/longitude until PostGIS is set up.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.products.models import Product


class Agrovet(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        VERIFIED = "verified"
        SUSPENDED = "suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agrovet")
    name = models.CharField(max_length=255)
    pcpb_licence_no = models.CharField(max_length=64)
    has_qualified_staff = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    trust_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta(TimeStampedModel.Meta):
        ordering = ("name",)

    def __str__(self):
        return self.name

    @property
    def is_verified(self) -> bool:
        return self.status == self.Status.VERIFIED


class StoreItem(TimeStampedModel):
    """One registered product in a verified agrovet's in-app store."""

    agrovet = models.ForeignKey(Agrovet, on_delete=models.CASCADE, related_name="store_items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="store_items")
    # Whole shillings: M-Pesa only accepts integer amounts.
    price_kes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    in_stock = models.BooleanField(default=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("agrovet", "product__name")
        constraints = [
            models.UniqueConstraint(fields=["agrovet", "product"], name="agrovets_one_item_per_product"),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.agrovet.name} (KES {self.price_kes})"
