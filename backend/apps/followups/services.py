"""Apply and Follow-up: the farmer records spraying and reports the crop on days 2, 4 and 7.

The farmer updates progress themselves in the app; nothing is sent to them. The final
check-in becomes the case's TreatmentOutcome (local evidence for the next farmer).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cases.models import Case
from apps.core.geo import haversine_km
from apps.diagnosis.models import FinalDiagnosis
from apps.prescriptions.models import TreatmentOutcome
from apps.prescriptions.services import LocalResult, local_results
from apps.purchases.models import Order, Verification
from apps.rewards.models import RewardEntry
from apps.rewards.services import award

from .models import CheckIn, SprayRecord

logger = logging.getLogger(__name__)

# A spray date a little in the future is clock skew on the phone, not a mistake.
CLOCK_SKEW = timedelta(minutes=10)


class FollowUpError(Exception):
    """A rule was broken by the request. ``status`` is the HTTP status the API returns."""

    status = 400

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class FollowUpNotFound(FollowUpError):
    status = 404


class FollowUpConflict(FollowUpError):
    status = 409


def check_in_days() -> list[int]:
    return sorted(settings.FOLLOWUP["CHECK_IN_DAYS"])


def final_day() -> int:
    return check_in_days()[-1]


# --- Spraying -------------------------------------------------------------------------


def verified_order(case: Case) -> Order | None:
    """The collected order whose label check verified the product, if any."""
    return (
        Order.objects.filter(
            prescription__case=case,
            status=Order.Status.COLLECTED,
            verifications__type=Verification.Type.LABEL_CHECK,
            verifications__result=Verification.Result.VERIFIED,
        )
        .select_related("product")
        .order_by("-collected_at")
        .first()
    )


def _own_case(farmer, case: Case) -> None:
    if case.farmer_id != farmer.pk:
        raise FollowUpNotFound("Case not found.", code="case_not_found")


def record_spray(*, farmer, case: Case, sprayed_at=None, amount_used: str = "") -> SprayRecord:
    """Start the follow-up. Only for a verified purchase (Documentation §11)."""
    _own_case(farmer, case)
    order = verified_order(case) if case.status == Case.Status.VERIFIED else None
    if order is None:
        raise FollowUpConflict(
            "Follow-up starts after the product's label check is verified.", code="not_verified"
        )
    now = timezone.now()
    sprayed_at = sprayed_at or now
    if sprayed_at > now + CLOCK_SKEW:
        raise FollowUpError("The spray date cannot be in the future.", code="future_date")
    if order.collected_at and sprayed_at < order.collected_at - CLOCK_SKEW:
        raise FollowUpError(
            "The spray date cannot be before you collected the product.", code="before_purchase"
        )

    final = FinalDiagnosis.objects.get(case=case)
    try:
        with transaction.atomic():
            record = SprayRecord.objects.create(
                case=case,
                order=order,
                farmer=farmer,
                product=order.product,
                disease=final.disease,
                sprayed_at=sprayed_at,
                amount_used=amount_used.strip(),
                baseline_share_affected=(case.symptom_answers or {}).get("share_affected", ""),
                ward=case.ward,
                latitude=case.latitude,
                longitude=case.longitude,
            )
    except IntegrityError as exc:
        raise FollowUpConflict("Spraying is already recorded for this case.", code="already_sprayed") from exc
    logger.info("Case %s sprayed with %s at %s", case.id, order.product.name, sprayed_at)
    return record


# --- Schedule ---------------------------------------------------------------------------


def due_at(record: SprayRecord, day: int):
    return record.sprayed_at + timedelta(days=day)


def closes_at(record: SprayRecord):
    """After this, check-ins are no longer accepted: late memories are not evidence."""
    return record.sprayed_at + timedelta(days=settings.FOLLOWUP["CLOSE_AFTER_DAYS"])


def schedule(record: SprayRecord, now=None) -> list[dict]:
    now = now or timezone.now()
    done = {c.day: c for c in record.check_ins.all()}
    items = []
    for day in check_in_days():
        if day in done:
            status = "done"
        elif record.completed_at or now >= closes_at(record):
            status = "missed"
        elif now >= due_at(record, day):
            status = "due"
        else:
            status = "upcoming"
        items.append({"day": day, "due_at": due_at(record, day), "status": status, "check_in": done.get(day)})
    return items


def harvest_safe_from(record: SprayRecord):
    """Pre-harvest interval countdown from the product label."""
    if record.product.phi_days is None:
        return None
    return record.sprayed_at + timedelta(days=record.product.phi_days)


# --- Check-ins ----------------------------------------------------------------------------


def add_check_in(
    *, farmer, case: Case, day: int, new_spots: str, share_affected: str, photo=None, notes: str = ""
) -> CheckIn:
    _own_case(farmer, case)
    record = SprayRecord.objects.filter(case=case).select_related("product").first()
    if record is None:
        raise FollowUpConflict("Record when you sprayed first.", code="not_sprayed")
    if day not in check_in_days():
        raise FollowUpError(
            f"Check-ins are on days {', '.join(map(str, check_in_days()))}.", code="invalid_day"
        )
    now = timezone.now()
    if record.completed_at or now >= closes_at(record):
        raise FollowUpConflict("This follow-up is closed.", code="follow_up_closed")
    if now < due_at(record, day):
        raise FollowUpConflict(f"Check your crop again on day {day} after spraying.", code="too_early")

    try:
        with transaction.atomic():
            check_in = CheckIn(
                spray_record=record,
                day=day,
                new_spots=new_spots,
                share_affected=share_affected,
                notes=notes.strip(),
            )
            if photo is not None:
                check_in.photo.save(f"day{day}.jpg", photo, save=False)
            check_in.save()
            if day == final_day():
                _complete(record)
    except IntegrityError as exc:
        raise FollowUpConflict(f"Day {day} is already recorded.", code="already_checked_in") from exc
    logger.info("Case %s day %s check-in: %s, %s affected", case.id, day, new_spots, share_affected)
    return check_in


def _complete(record: SprayRecord) -> TreatmentOutcome:
    """Turn the final check-in into the case's outcome, and thank the farmer with points."""
    check_ins = list(record.check_ins.all())
    final = next(c for c in check_ins if c.day == final_day())
    stopped_days = [c.day for c in check_ins if c.spread_stopped]
    outcome, _ = TreatmentOutcome.objects.update_or_create(
        case=record.case,
        defaults={
            "farmer": record.farmer,
            "disease": record.disease,
            "product": record.product,
            "improved": final.spread_stopped,
            "days_after_spraying": min(stopped_days) if final.spread_stopped and stopped_days else None,
            "ward": record.ward,
            "latitude": record.latitude,
            "longitude": record.longitude,
        },
    )
    record.completed_at = timezone.now()
    record.save(update_fields=["completed_at", "updated_at"])
    award(
        farmer=record.farmer,
        reason=RewardEntry.Reason.FOLLOW_UP,
        points=settings.FOLLOWUP["REWARD_POINTS"],
        source_ref=f"case:{record.case_id}",
    )
    return outcome


# --- Expected results for this farmer -----------------------------------------------------------


def _nearby(case: Case, ward: str, latitude, longitude) -> bool:
    if case.ward and ward and case.ward.lower() == ward.lower():
        return True
    if None in (case.latitude, case.longitude, latitude, longitude):
        return False
    return (
        haversine_km(case.latitude, case.longitude, latitude, longitude)
        <= settings.PRESCRIBE["OUTCOME_RADIUS_KM"]
    )


def response_rate(case: Case, disease, product) -> float | None:
    """Share of nearby farmers who finished the follow-up, among those whose follow-up has closed.

    Farmers whose spray failed often stop reporting, so a low rate means results look better than they are.
    """
    closed_before = timezone.now() - timedelta(days=settings.FOLLOWUP["CLOSE_AFTER_DAYS"])
    records = [
        r
        for r in SprayRecord.objects.filter(disease=disease, product=product, sprayed_at__lt=closed_before)
        if r.case_id != case.id and _nearby(case, r.ward, r.latitude, r.longitude)
    ]
    if not records:
        return None
    return round(sum(r.completed_at is not None for r in records) / len(records), 2)


def expected_results(case: Case, disease, product) -> dict:
    """What happened for verified farmers nearby with the same disease and product."""
    result = local_results(case, disease, [product]).get(product.id, LocalResult(0, 0, None))
    return {
        "product": product.name,
        "enough_data": result.enough,
        "improved": result.improved if result.enough else None,
        "reported": result.reported if result.enough else None,
        "typical_day": result.typical_day if result.enough else None,
        "response_rate": response_rate(case, disease, product) if result.enough else None,
        "text": result.text,
    }
