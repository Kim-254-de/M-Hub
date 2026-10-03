"""Apply and Follow-up (Documentation §14, Phase 2): the farmer records spraying and how the crop responds.

The final check-in becomes the case's TreatmentOutcome, which the next farmer sees as local
results and which ranks products in Prescribe.
"""

from django.conf import settings
from django.db import models

from apps.cases.models import Case
from apps.core.models import TimeStampedModel
from apps.products.models import Disease, Product


def check_in_photo_upload_to(instance, filename):
    return f"follow_ups/{instance.spray_record.case_id}/day{instance.day}_{instance.id}.jpg"


class ShareAffected(models.TextChoices):
    """Same choices as the Detect quick questions, so before and after can be compared."""

    FEW = "few"  # under 10% of plants
    SOME = "some"  # 10-50%
    MOST = "most"  # over 50%


SHARE_ORDER = {ShareAffected.FEW: 0, ShareAffected.SOME: 1, ShareAffected.MOST: 2}


class SprayRecord(TimeStampedModel):
    """The farmer sprayed the verified product. Starts the day 2/4/7 follow-up."""

    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="spray_record")
    order = models.ForeignKey("purchases.Order", on_delete=models.PROTECT, related_name="+")
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="spray_records"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    disease = models.ForeignKey(Disease, on_delete=models.PROTECT, related_name="+")
    sprayed_at = models.DateTimeField()
    amount_used = models.CharField(
        max_length=128, blank=True, help_text='As the farmer says, e.g. "half the pack"'
    )
    # Share of plants affected when the problem was reported (Detect quick questions).
    baseline_share_affected = models.CharField(max_length=8, choices=ShareAffected.choices, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Final check-in recorded")
    # Copied from the case so local results do not need joins.
    ward = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["disease", "product", "sprayed_at"])]

    def __str__(self):
        return f"{self.product} sprayed for case {self.case_id}"


class CheckIn(TimeStampedModel):
    """The farmer's report on day 2, 4 or 7 after spraying."""

    class NewSpots(models.TextChoices):
        SPREADING = "spreading", "Yes, still spreading"
        FEWER = "fewer", "A few new spots"
        STOPPED = "stopped", "No new spots"

    spray_record = models.ForeignKey(SprayRecord, on_delete=models.CASCADE, related_name="check_ins")
    day = models.PositiveSmallIntegerField()
    new_spots = models.CharField(max_length=16, choices=NewSpots.choices)
    share_affected = models.CharField(max_length=8, choices=ShareAffected.choices)
    photo = models.ImageField(upload_to=check_in_photo_upload_to, null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ("day",)
        constraints = [
            models.UniqueConstraint(fields=["spray_record", "day"], name="followups_one_check_in_per_day"),
        ]

    def __str__(self):
        return f"Day {self.day} for case {self.spray_record.case_id}: {self.new_spots}"

    @property
    def spread_stopped(self) -> bool:
        """No new spots, and no more of the crop affected than when the problem was reported."""
        baseline = self.spray_record.baseline_share_affected
        not_worse = not baseline or SHARE_ORDER[self.share_affected] <= SHARE_ORDER[baseline]
        return self.new_spots == self.NewSpots.STOPPED and not_worse
