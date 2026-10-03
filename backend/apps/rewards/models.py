from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class RewardEntry(TimeStampedModel):
    """Append-only points ledger (Documentation §6.5, §9.2 `rewards`).

    A farmer's balance is the sum of their entries. Redemptions are negative entries.
    """

    class Reason(models.TextChoices):
        VERIFIED_PURCHASE = "verified_purchase"
        CASE_REPORTED = "case_reported"
        REFERRAL = "referral"
        REDEMPTION = "redemption"

    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reward_entries"
    )
    reason = models.CharField(max_length=32, choices=Reason.choices)
    points = models.IntegerField()
    # What earned the points, e.g. "order:<uuid>". Unique per reason so nothing is awarded twice.
    source_ref = models.CharField(max_length=64)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "reward entries"
        constraints = [
            models.UniqueConstraint(fields=["reason", "source_ref"], name="rewards_unique_source_per_reason"),
        ]
        indexes = [models.Index(fields=["farmer", "-created_at"])]

    def __str__(self):
        return f"{self.points:+d} {self.reason} for {self.farmer_id}"
