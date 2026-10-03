import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Sum

from .models import RewardEntry, TrustEvent

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


def adjust_trust(*, user, reason: str, delta, source_ref: str) -> TrustEvent | None:
    """Change a farmer's or agrovet's trust score once per (user, reason, source_ref).

    Returns None if this change was already applied.
    """
    from apps.accounts.models import FarmerProfile
    from apps.agrovets.models import Agrovet

    delta = Decimal(str(delta))
    try:
        with transaction.atomic():
            event = TrustEvent.objects.create(user=user, reason=reason, delta=delta, source_ref=source_ref)
            Agrovet.objects.filter(user=user).update(trust_score=F("trust_score") + delta)
            FarmerProfile.objects.filter(user=user).update(trust_score=F("trust_score") + delta)
    except IntegrityError:
        logger.info("Trust change %s for %s already applied", reason, source_ref)
        return None
    logger.info("Trust %+s (%s) for user %s", delta, reason, user.pk)
    return event
