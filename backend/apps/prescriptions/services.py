"""Module 3: Prescribe (Documentation §6.3, §8.4).

4.1 allowed_products   4.2 rank_products   4.3 calculate_dose
4.4 approve (agrovet review)               4.5 code + expiry (inside approve)

Guardrails (§11): the registered-products rule cannot be overridden, the agrovet can only
swap between allowed products, and local evidence only ranks; it never adds products or
changes doses.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Avg
from django.utils import timezone

from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.cases.services import transition
from apps.core.geo import haversine_km
from apps.diagnosis.models import FinalDiagnosis
from apps.notifications import events
from apps.products.models import Disease, Product
from apps.rewards.models import TrustEvent
from apps.rewards.services import adjust_trust

from .messages import format_amount
from .models import Prescription, TreatmentOutcome

logger = logging.getLogger(__name__)

CROP = "tomato"


# --- Errors -------------------------------------------------------------------


class PrescribeError(Exception):
    """A rule was broken by the request. ``status`` is the HTTP status the API returns."""

    status = 400

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class PrescribeNotFound(PrescribeError):
    status = 404


class PrescribeConflict(PrescribeError):
    status = 409


class PrescribePermissionDenied(PrescribeError):
    status = 403


# --- 4.1 Filter allowed products --------------------------------------------------


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def allowed_products(disease: Disease, crop: str = CROP) -> list[Product]:
    """Registered products approved for the crop that contain an ingredient recommended for the disease.

    Done in Python: the register is small, and JSON array lookups differ between databases.
    """
    ingredients = {
        _norm(i)
        for i in disease.treatment_rules.filter(crop__iexact=crop).values_list("active_ingredient", flat=True)
    }
    if not ingredients:
        return []
    allowed = []
    for product in Product.objects.filter(is_active=True):
        crops = {_norm(c) for c in product.approved_crops or []}
        product_ingredients = {_norm(i) for i in product.active_ingredients or []}
        if _norm(crop) in crops and product_ingredients & ingredients:
            allowed.append(product)
    return allowed


# --- 4.2 Rank by local evidence ---------------------------------------------------


@dataclass(frozen=True)
class LocalResult:
    """Final day-7 follow-ups for one product and disease from verified purchases nearby."""

    improved: int
    reported: int
    # Median day on which those who improved first reported the spread stopping.
    typical_day: int | None

    @property
    def enough(self) -> bool:
        return self.reported >= settings.PRESCRIBE["MIN_LOCAL_OUTCOMES"]

    @property
    def text(self) -> str:
        if not self.enough:
            return "Not enough local data yet"
        text = f"{self.improved} of {self.reported} verified farmers nearby saw the spread stop"
        return text + (f", usually by day {self.typical_day}" if self.typical_day else "")


def local_results(case: Case, disease: Disease, products: list[Product]) -> dict:
    """{product_id: LocalResult} for products with any nearby outcome (same ward or within the radius)."""
    config = settings.PRESCRIBE
    since = timezone.now() - timedelta(days=config["OUTCOME_WINDOW_DAYS"])
    outcomes = TreatmentOutcome.objects.filter(
        disease=disease,
        product__in=products,
        created_at__gte=since,
        # Verified purchase required before a report counts as evidence (§11).
        case__status=Case.Status.VERIFIED,
    )
    grouped: dict = {}
    for o in outcomes:
        same_ward = case.ward and o.ward and case.ward.lower() == o.ward.lower()
        close = None not in (case.latitude, case.longitude, o.latitude, o.longitude) and (
            haversine_km(case.latitude, case.longitude, o.latitude, o.longitude)
            <= config["OUTCOME_RADIUS_KM"]
        )
        if same_ward or close:
            grouped.setdefault(o.product_id, []).append(o)

    results = {}
    for product_id, items in grouped.items():
        days = [o.days_after_spraying for o in items if o.improved and o.days_after_spraying]
        results[product_id] = LocalResult(
            improved=sum(o.improved for o in items),
            reported=len(items),
            typical_day=round(statistics.median(days)) if days else None,
        )
    return results


def _average_prices(products: list[Product]) -> dict:
    rows = (
        StoreItem.objects.filter(product__in=products, agrovet__status=Agrovet.Status.VERIFIED)
        .values("product_id")
        .annotate(avg=Avg("price_kes"))
    )
    return {row["product_id"]: round(row["avg"]) for row in rows}


def rank_products(case: Case, disease: Disease, products: list[Product]) -> list[dict]:
    """Order allowed products: by local improvement rate where there is enough evidence,
    then by label guidance (shortest pre-harvest interval first)."""
    results = local_results(case, disease, products)
    prices = _average_prices(products)

    options = []
    for product in products:
        result = results.get(product.id, LocalResult(0, 0, None))
        has_evidence = result.enough
        improved, total = result.improved, result.reported
        options.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                "local_evidence": has_evidence,
                "improved": improved if has_evidence else None,
                "reported": total if has_evidence else None,
                "typical_day": result.typical_day if has_evidence else None,
                "evidence_text": result.text,
                "avg_price_kes": prices.get(product.id),
                "_sort": (
                    0 if has_evidence else 1,
                    -(improved / total) if has_evidence else 0,
                    -total,
                    product.phi_days if product.phi_days is not None else math.inf,
                    product.name.lower(),
                ),
            }
        )
    options.sort(key=lambda o: o.pop("_sort"))
    for rank, option in enumerate(options, start=1):
        option["rank"] = rank
    return options


# --- 4.3 Calculate dose --------------------------------------------------------------


@dataclass(frozen=True)
class Dose:
    quantity: str  # what the farmer buys, e.g. "1 pack of 250 g (125 g needed)"
    amount: Decimal | None
    unit: str
    packs: int | None
    follow_label: bool  # no numeric rate or farm size: the farmer follows the label
    pack_size: Decimal | None = None


def calculate_dose(product: Product, size_acres: Decimal | None) -> Dose:
    """Quantity for one spray of the farm: farm size x label rate, rounded up to whole packs."""
    if not product.rate_per_acre or not product.rate_unit or not size_acres:
        label = product.label_rate or "the rate on the label"
        return Dose(
            quantity=f"Follow the label: {label}",
            amount=None,
            unit=product.rate_unit,
            packs=None,
            follow_label=True,
        )

    amount = Decimal(size_acres) * product.rate_per_acre
    unit = product.rate_unit
    if product.pack_size:
        packs = max(1, math.ceil(amount / product.pack_size))
        pack_word = "pack" if packs == 1 else "packs"
        pack = format_amount(product.pack_size)
        quantity = f"{packs} {pack_word} of {pack} {unit} ({format_amount(amount)} {unit} needed)"
    else:
        packs = None
        quantity = f"{format_amount(amount)} {unit}"
    return Dose(
        quantity=quantity,
        amount=amount,
        unit=unit,
        packs=packs,
        follow_label=False,
        pack_size=product.pack_size if packs else None,
    )


# --- Draft (4.1-4.3) for the agrovet ------------------------------------------------


def _final_diagnosis(case: Case) -> FinalDiagnosis:
    final = FinalDiagnosis.objects.select_related("disease", "confirmed_by").filter(case=case).first()
    if final is None:
        raise PrescribeConflict("This case has no confirmed diagnosis.", code="not_diagnosed")
    return final


def get_prescribing_agrovet(user, case: Case) -> Agrovet:
    """The verified agrovet who confirmed the diagnosis approves the prescription (4.4)."""
    agrovet = getattr(user, "agrovet", None)
    if agrovet is None or not agrovet.is_verified:
        raise PrescribePermissionDenied("Only verified agrovets can do this.", code="agrovet_not_verified")
    final = FinalDiagnosis.objects.filter(case=case).first()
    if final is None or final.confirmed_by_id != agrovet.id:
        raise PrescribeNotFound("Case not found.", code="case_not_found")
    return agrovet


def build_draft(case: Case) -> dict:
    """The draft prescription the agrovet reviews: allowed, ranked options with doses."""
    final = _final_diagnosis(case)
    products = allowed_products(final.disease)
    size_acres = case.farm.size_acres if case.farm_id else None
    by_id = {str(p.id): p for p in products}

    options = rank_products(case, final.disease, products)
    for option in options:
        product = by_id[option["product_id"]]
        dose = calculate_dose(product, size_acres)
        option.update(
            {
                "pcpb_reg_no": product.pcpb_reg_no,
                "active_ingredients": product.active_ingredients,
                "quantity": dose.quantity,
                "follow_label": dose.follow_label,
                "dose": dose,
                "phi_days": product.phi_days,
                "ppe_notes": product.ppe_notes,
            }
        )
    return {
        "case_id": str(case.id),
        "disease": {"id": str(final.disease.id), "name": final.disease.name},
        "farm_size_acres": size_acres,
        "local_data": any(o["local_evidence"] for o in options),
        "options": options,
    }


# --- 4.4 Agrovet approval, 4.5 issue code ------------------------------------------------


def approve(*, agrovet_user, case: Case, product_id) -> Prescription:
    """The agrovet approves the top option or swaps to another allowed one; the code is issued."""
    agrovet = get_prescribing_agrovet(agrovet_user, case)
    with transaction.atomic():
        case = Case.objects.select_for_update().select_related("farm").get(pk=case.pk)
        if case.status != Case.Status.DIAGNOSED:
            raise PrescribeConflict(
                f"This case is {case.status} and cannot be prescribed.", code="case_not_diagnosed"
            )
        if Prescription.objects.filter(case=case).exists():
            raise PrescribeConflict("This case already has a prescription.", code="already_prescribed")

        draft = build_draft(case)
        if not draft["options"]:
            raise PrescribeConflict(
                "No registered product is approved for this disease on tomato. Advise the farmer without a "
                "prescription.",
                code="no_allowed_products",
            )
        chosen = next((o for o in draft["options"] if o["product_id"] == str(product_id)), None)
        if chosen is None:
            # The rule filter cannot be overridden (§11).
            raise PrescribeError(
                "This product is not allowed for this diagnosis.", code="product_not_allowed"
            )

        ranking = [
            {
                k: o[k]
                for k in (
                    "rank",
                    "product_id",
                    "name",
                    "local_evidence",
                    "improved",
                    "reported",
                    "avg_price_kes",
                )
            }
            for o in draft["options"]
        ]
        prescription = _create_with_unique_code(
            case=case,
            disease_id=draft["disease"]["id"],
            approved_product_id=chosen["product_id"],
            quantity=chosen["quantity"][:128],
            dose_amount=chosen["dose"].amount,
            dose_unit=chosen["dose"].unit,
            dose_packs=chosen["dose"].packs,
            dose_pack_size=chosen["dose"].pack_size,
            approved_by=agrovet,
            expires_at=timezone.now() + timedelta(days=settings.PRESCRIBE["EXPIRY_DAYS"]),
            ranking=ranking,
        )
        prescription.allowed_products.set([o["product_id"] for o in draft["options"]])
        transition(case.id, from_statuses=[Case.Status.DIAGNOSED], to=Case.Status.PRESCRIBED)
        case.status = Case.Status.PRESCRIBED
        # The code by SMS too, so farmers can buy without opening the app.
        events.prescription_issued(prescription)

    logger.info(
        "Prescription %s issued for case %s: %s (rank %s of %s)",
        prescription.code,
        case.id,
        chosen["name"],
        chosen["rank"],
        len(ranking),
    )
    return prescription


def _create_with_unique_code(**fields) -> Prescription:
    for attempt in range(3):
        try:
            with transaction.atomic():
                return Prescription.objects.create(**fields)
        except IntegrityError:
            if attempt == 2:
                raise
            logger.warning("Prescription code collision; retrying")
    raise AssertionError("unreachable")


# --- Conflict-of-interest monitoring (§6.3) -------------------------------------------------


def favours_price_over_evidence(ranking: list[dict], chosen_product_id) -> bool:
    """True when a better-performing option (with local evidence) was ranked above the chosen
    one and the chosen one costs more."""
    chosen = next((o for o in ranking if o["product_id"] == str(chosen_product_id)), None)
    if chosen is None or chosen.get("avg_price_kes") is None:
        return False
    for option in ranking:
        if option["rank"] >= chosen["rank"]:
            break
        if option["local_evidence"] and option.get("avg_price_kes") is not None:
            if chosen["avg_price_kes"] > option["avg_price_kes"]:
                return True
    return False


def review_prescribing_patterns() -> int:
    """Periodic: lower the trust score of agrovets who consistently favour price over evidence.

    Applied at most once per agrovet per calendar quarter. Returns how many were penalised.
    """
    config = settings.PRESCRIBE
    now = timezone.now()
    since = now - timedelta(days=config["COI_WINDOW_DAYS"])
    quarter = f"{now.year}-Q{(now.month - 1) // 3 + 1}"

    by_agrovet: dict = {}
    for p in (
        Prescription.objects.filter(created_at__gte=since)
        .exclude(ranking=[])
        .select_related("approved_by__user")
    ):
        stats = by_agrovet.setdefault(p.approved_by_id, {"agrovet": p.approved_by, "total": 0, "flagged": 0})
        stats["total"] += 1
        stats["flagged"] += int(favours_price_over_evidence(p.ranking, p.approved_product_id))

    penalised = 0
    for stats in by_agrovet.values():
        if (
            stats["total"] < config["COI_MIN_PRESCRIPTIONS"]
            or stats["flagged"] / stats["total"] < config["COI_SHARE"]
        ):
            continue
        event = adjust_trust(
            user=stats["agrovet"].user,
            reason=TrustEvent.Reason.PRESCRIBING_PATTERN,
            delta=settings.TRUST["PRESCRIBING_PATTERN"],
            source_ref=f"coi:{quarter}",
        )
        if event is not None:
            penalised += 1
            logger.warning(
                "Agrovet %s favoured pricier options over evidence in %s of %s prescriptions",
                stats["agrovet"].id,
                stats["flagged"],
                stats["total"],
            )
    return penalised
