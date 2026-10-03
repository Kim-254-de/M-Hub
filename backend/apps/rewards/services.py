import logging

from django.db import IntegrityError, transaction
from django.db.models import Sum

from .models import RewardEntry

logger = logging.getLogger(__name__)


def award(*, farmer, reason: str, points: int, source_ref: str) -> RewardEntry | None:
    """Award points once per (reason, source_ref). Returns None if already awarded."""
    try:
        with transaction.atomic():
            entry = RewardEntry.objects.create(
                farmer=farmer, reason=reason, points=points, source_ref=source_ref
            )
    except IntegrityError:
        logger.info("Reward %s for %s already awarded", reason, source_ref)
        return None
    logger.info("Awarded %s points (%s) to farmer %s", points, reason, farmer.pk)
    return entry


def balance(farmer) -> int:
    return RewardEntry.objects.filter(farmer=farmer).aggregate(total=Sum("points"))["total"] or 0
