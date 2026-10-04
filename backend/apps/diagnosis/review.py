"""Diagnose module, processes 3.2-3.6: evidence, agrovet confirmation and second opinions.

3.2 similar_cases          3.3 add_peer_comment / peer_summary
3.4 assign_review / decide 3.5 agreement check (inside decide)   3.6 second opinion (inside decide)

The AI only suggests; every diagnosis is made by a verified agrovet (Documentation §11).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import FarmerProfile, User
from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.cases.services import transition
from apps.core.geo import haversine_km
from apps.notifications import events
from apps.products.models import Disease
from apps.rewards.models import TrustEvent
from apps.rewards.services import adjust_trust

from .models import AgrovetReview, AIDiagnosis, FinalDiagnosis, PeerComment

logger = logging.getLogger(__name__)

REVIEWABLE_STATUSES = (Case.Status.DIAGNOSING, Case.Status.SECOND_OPINION)
ROUND_FOR_STATUS = {
    Case.Status.DIAGNOSING: AgrovetReview.Round.FIRST,
    Case.Status.SECOND_OPINION: AgrovetReview.Round.SECOND_OPINION,
}
HEALTHY = "healthy"


# --- Errors -------------------------------------------------------------------


class DiagnoseError(Exception):
    """A rule was broken by the request. ``status`` is the HTTP status the API returns."""

    status = 400

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class DiagnoseNotFound(DiagnoseError):
    status = 404


class DiagnoseConflict(DiagnoseError):
    status = 409


class DiagnosePermissionDenied(DiagnoseError):
    status = 403


# --- Disease matching -----------------------------------------------------------


def match_disease(suggestion, diseases: list[Disease] | None = None) -> Disease | None:
    """The catalogue disease an AI suggestion refers to, by provider id or name."""
    if diseases is None:
        diseases = list(Disease.objects.filter(is_active=True))
    names = {suggestion.name.strip().lower(), (suggestion.scientific_name or "").strip().lower()} - {""}
    for disease in diseases:
        if suggestion.external_id and suggestion.external_id in (disease.provider_ids or []):
            return disease
    for disease in diseases:
        if disease.name.lower() in names or (
            disease.scientific_name and disease.scientific_name.lower() in names
        ):
            return disease
    return None


def _latest_completed_ai(case: Case) -> AIDiagnosis | None:
    return (
        AIDiagnosis.objects.filter(case=case, status=AIDiagnosis.Status.COMPLETED)
        .prefetch_related("suggestions")
        .order_by("-created_at")
        .first()
    )


# --- 3.1 output, as one evidence source ----------------------------------------


def ai_opinion(case: Case) -> dict:
    """The AI top suggestion as an opinion for the agreement check.

    ``opinion`` is a disease id, ``"healthy"``, or None when the AI cannot be compared:
    no completed run, a low-probability top suggestion, or a disease not in the catalogue.
    """
    ai = _latest_completed_ai(case)
    if ai is None:
        return {"available": False, "opinion": None, "reason": "no_ai_result"}
    suggestions = list(ai.suggestions.all())
    if not suggestions:
        return {"available": False, "opinion": None, "reason": "no_suggestions"}

    diseases = list(Disease.objects.filter(is_active=True))
    top = suggestions[0]
    matched = None if top.is_healthy else match_disease(top, diseases)
    result = {
        "name": top.name,
        "probability": float(top.probability),
        "disease_id": str(matched.id) if matched else None,
        "candidate_disease_ids": [
            str(d.id) for d in (match_disease(s, diseases) for s in suggestions if not s.is_healthy) if d
        ],
    }
    if top.probability < Decimal(str(settings.DIAGNOSE["AI_MIN_PROBABILITY_FOR_AGREEMENT"])):
        return {**result, "available": False, "opinion": None, "reason": "low_probability"}
    if top.is_healthy:
        return {**result, "available": True, "opinion": HEALTHY}
    if matched is None:
        return {**result, "available": False, "opinion": None, "reason": "not_in_catalogue"}
    return {**result, "available": True, "opinion": str(matched.id)}


# --- Provisional result for the farmer (while waiting for 3.4) ----------------------------

PROVISIONAL_STATUSES = (Case.Status.REPORTED, Case.Status.DIAGNOSING)


def ai_evidence(case: Case, language: str) -> dict | None:
    """After confirmation: the AI's top suggestion, shown as supporting evidence next to the agrovet's
    confirmation ("AI suggestion: Late blight (87%)"). None when there was no usable AI result."""
    ai = _latest_completed_ai(case)
    if ai is None or ai.needs_retake:
        return None
    top = next(iter(ai.suggestions.all()), None)
    if top is None or top.is_healthy:
        return None
    disease = match_disease(top)
    return {
        "name": disease.display_name(language) if disease else top.name,
        "percent": round(float(top.probability) * 100),
    }


def provisional_result(case: Case) -> dict | None:
    """The AI suggestion as the farmer sees it before an agrovet confirms.

    ``kind`` is ``likely`` (names a disease), ``healthy`` or ``unsure``. None when there is
    nothing to show: the AI has not finished, photos must be retaken, or the case has moved on
    (a second opinion means the AI and the agrovet disagreed, so the AI is not repeated).
    Never includes products: those come only from an approved prescription.
    """
    if case.status not in PROVISIONAL_STATUSES:
        return None
    ai = _latest_completed_ai(case)
    if ai is None or ai.needs_retake:
        return None
    suggestions = list(ai.suggestions.all())
    top = suggestions[0] if suggestions else None
    minimum = Decimal(str(settings.DIAGNOSE["AI_MIN_PROBABILITY_FOR_PROVISIONAL"]))
    if top is None or top.probability < minimum:
        return {"kind": "unsure", "disease": None, "name": None, "probability": None}
    probability = float(top.probability)
    if top.is_healthy:
        return {"kind": "healthy", "disease": None, "name": None, "probability": probability}
    disease = match_disease(top)
    if disease is None and not settings.DIAGNOSE["NAME_DISEASES_OUTSIDE_CATALOGUE"]:
        return {"kind": "unsure", "disease": None, "name": None, "probability": None}
    return {"kind": "likely", "disease": disease, "name": top.name, "probability": probability}


def ai_corrected(case: Case, final: FinalDiagnosis) -> bool | None:
    """Whether the confirmed disease differs from the AI's top suggestion. None without an AI result."""
    ai = _latest_completed_ai(case)
    top = next(iter(ai.suggestions.all()), None) if ai else None
    if top is None:
        return None
    if top.is_healthy:
        return True
    matched = match_disease(top)
    return matched is None or matched.id != final.disease_id


# --- 3.2 Similar past cases ------------------------------------------------------


def _is_nearby(case: Case, ward: str, latitude, longitude, radius_km: float) -> bool:
    if case.ward and ward and case.ward.lower() == ward.lower():
        return True
    if None in (case.latitude, case.longitude, latitude, longitude):
        return False
    return haversine_km(case.latitude, case.longitude, latitude, longitude) <= radius_km


def similar_cases(case: Case, ai: dict | None = None) -> dict:
    """Confirmed cases nearby and recent, limited to the AI's suggested diseases when there are any.

    Returns per-disease counts and the majority disease, which only counts in the
    agreement check when backed by enough cases.
    """
    config = settings.DIAGNOSE
    ai = ai if ai is not None else ai_opinion(case)
    since = timezone.now() - timedelta(days=config["SIMILAR_CASES_WINDOW_DAYS"])

    qs = FinalDiagnosis.objects.filter(created_at__gte=since).exclude(case=case).select_related("disease")
    candidates = ai.get("candidate_disease_ids") or []
    if candidates:
        qs = qs.filter(disease_id__in=candidates)

    counts: dict[str, dict] = {}
    for final in qs:
        if not _is_nearby(
            case, final.ward, final.latitude, final.longitude, config["SIMILAR_CASES_RADIUS_KM"]
        ):
            continue
        entry = counts.setdefault(
            str(final.disease_id),
            {"disease_id": str(final.disease_id), "name": final.disease.name, "count": 0},
        )
        entry["count"] += 1

    by_disease = sorted(counts.values(), key=lambda e: -e["count"])
    total = sum(e["count"] for e in by_disease)
    majority = None
    if by_disease:
        top = by_disease[0]
        if top["count"] >= config["SIMILAR_CASES_MIN_FOR_AGREEMENT"] and top["count"] * 2 > total:
            majority = top["disease_id"]
    return {
        "total": total,
        "by_disease": by_disease,
        "window_days": config["SIMILAR_CASES_WINDOW_DAYS"],
        "available": majority is not None,
        "opinion": majority,
    }


# --- 3.3 Peer input ---------------------------------------------------------------


def verified_purchase_count(user) -> int:
    return Case.objects.filter(farmer=user, status=Case.Status.VERIFIED).count()


def peer_weight(profile: FarmerProfile) -> Decimal:
    """1 for a new trusted peer, growing with trust score."""
    return Decimal(1) + max(profile.trust_score, Decimal(0)) / Decimal(10)


def _peer_profile(user) -> FarmerProfile | None:
    if not user.is_authenticated or user.role != User.Role.FARMER:
        return None
    profile = FarmerProfile.objects.filter(user=user).first()
    if profile is None or not profile.ward:
        return None
    if verified_purchase_count(user) < settings.DIAGNOSE["PEER_MIN_VERIFIED_PURCHASES"]:
        return None
    return profile


def cases_open_for_peer(user):
    """Cases waiting for diagnosis in the farmer's ward that they may comment on."""
    profile = _peer_profile(user)
    if profile is None:
        return Case.objects.none()
    return (
        Case.objects.filter(status__in=REVIEWABLE_STATUSES, ward__iexact=profile.ward)
        .exclude(farmer=user)
        .exclude(peer_comments__farmer=user)
        .prefetch_related("photos")
        .order_by("-submitted_at")
    )


def add_peer_comment(*, user, case: Case, disease_id=None, comment: str = "") -> PeerComment:
    profile = _peer_profile(user)
    if profile is None:
        raise DiagnosePermissionDenied(
            "Only trusted farmers with a verified purchase can comment.", code="peer_not_eligible"
        )
    if case.farmer_id == user.pk or not case.ward or case.ward.lower() != profile.ward.lower():
        raise DiagnoseNotFound("Case not found.", code="case_not_found")
    if case.status not in REVIEWABLE_STATUSES:
        raise DiagnoseConflict("This case is no longer waiting for a diagnosis.", code="case_closed")
    disease = None
    if disease_id:
        disease = Disease.objects.filter(pk=disease_id, is_active=True).first()
        if disease is None:
            raise DiagnoseError("Unknown disease.", code="unknown_disease")
    if disease is None and not comment.strip():
        raise DiagnoseError("Choose a disease or write a comment.", code="empty_comment")
    try:
        with transaction.atomic():
            return PeerComment.objects.create(
                case=case, farmer=user, disease=disease, comment=comment.strip(), weight=peer_weight(profile)
            )
    except IntegrityError as exc:
        raise DiagnoseConflict("You have already commented on this case.", code="already_commented") from exc


def peer_summary(case: Case) -> dict:
    """Weighted peer votes per disease, plus the comments. Commenters stay anonymous."""
    comments = list(case.peer_comments.select_related("disease").order_by("created_at"))
    votes: dict[str, dict] = {}
    for c in comments:
        if c.disease_id:
            entry = votes.setdefault(
                str(c.disease_id),
                {"disease_id": str(c.disease_id), "name": c.disease.name, "weight": 0.0, "count": 0},
            )
            entry["weight"] += float(c.weight)
            entry["count"] += 1
    return {
        "count": len(comments),
        "by_disease": sorted(votes.values(), key=lambda e: -e["weight"]),
        "comments": [
            {
                "disease": c.disease.name if c.disease else None,
                "comment": c.comment,
                "weight": float(c.weight),
            }
            for c in comments
        ],
    }


def collect_evidence(case: Case) -> dict:
    """Everything the agrovet sees for a case (3.4)."""
    ai = ai_opinion(case)
    return {"ai": ai, "similar_cases": similar_cases(case, ai), "peers": peer_summary(case)}


# --- 3.4 / 3.6 Assignment ---------------------------------------------------------


def nearest_verified_agrovets(case: Case, *, exclude_ids=()) -> list[Agrovet]:
    agrovets = list(Agrovet.objects.filter(status=Agrovet.Status.VERIFIED).exclude(id__in=list(exclude_ids)))
    if case.latitude is None or case.longitude is None:
        return sorted(agrovets, key=lambda a: -a.trust_score)
    return sorted(
        agrovets,
        key=lambda a: (haversine_km(case.latitude, case.longitude, a.latitude, a.longitude), -a.trust_score),
    )


def _round_for(case: Case) -> int:
    # A farmer may pick their agrovet before the AI run finishes (case still REPORTED).
    return ROUND_FOR_STATUS.get(case.status, AgrovetReview.Round.FIRST)


def assign_review(case: Case) -> AgrovetReview | None:
    """Give a waiting case to the nearest verified agrovet who has not reviewed it yet.

    No-op if the case already has a pending review or no agrovet is available
    (the periodic task tries again).
    """
    with transaction.atomic():
        case = Case.objects.select_for_update().get(pk=case.pk)
        if case.status not in REVIEWABLE_STATUSES:
            return None
        pending = (
            case.agrovet_reviews.filter(status=AgrovetReview.Status.PENDING).select_related("agrovet").first()
        )
        if pending is not None:
            # E.g. the farmer picked this agrovet before the AI finished; tell them now it is reviewable.
            events.review_assigned(pending)
            return None
        already = case.agrovet_reviews.values_list("agrovet_id", flat=True)
        candidates = nearest_verified_agrovets(case, exclude_ids=already)
        if not candidates:
            logger.warning("No verified agrovet available for case %s (%s)", case.id, case.status)
            return None
        review = AgrovetReview.objects.create(case=case, agrovet=candidates[0], round=_round_for(case))
        events.review_assigned(review)
    logger.info("Case %s assigned to agrovet %s (round %s)", case.id, review.agrovet_id, review.round)
    return review


def assign_review_after_commit(case_id) -> None:
    """Schedule assignment once the surrounding transaction commits; never fails the caller."""

    def _assign():
        try:
            assign_review(Case.objects.get(pk=case_id))
        except Exception:
            logger.exception("Assigning a reviewer to case %s failed; the periodic task will retry", case_id)

    transaction.on_commit(_assign)


def choose_agrovet(*, farmer, case: Case, agrovet_id) -> AgrovetReview:
    """The farmer picks which verified agrovet confirms their diagnosis (§6.2 step 4)."""
    if case.farmer_id != farmer.pk:
        raise DiagnoseNotFound("Case not found.", code="case_not_found")
    agrovet = Agrovet.objects.filter(pk=agrovet_id, status=Agrovet.Status.VERIFIED).first()
    if agrovet is None:
        raise DiagnoseError("Choose a verified agrovet.", code="agrovet_not_verified")
    with transaction.atomic():
        case = Case.objects.select_for_update().get(pk=case.pk)
        if case.status not in (Case.Status.REPORTED, Case.Status.DIAGNOSING):
            raise DiagnoseConflict("The agrovet can no longer be changed for this case.", code="case_closed")
        reviews = case.agrovet_reviews.select_for_update()
        if reviews.filter(status=AgrovetReview.Status.DECIDED).exists():
            raise DiagnoseConflict("An agrovet has already reviewed this case.", code="already_reviewed")
        current = reviews.filter(status=AgrovetReview.Status.PENDING).first()
        if current is not None and current.agrovet_id == agrovet.id:
            return current
        if reviews.filter(agrovet=agrovet).exists():
            raise DiagnoseConflict(
                "This agrovet did not respond to this case. Choose another.", code="agrovet_unavailable"
            )
        if current is not None:
            current.status = AgrovetReview.Status.WITHDRAWN
            current.save(update_fields=["status", "updated_at"])
        review = AgrovetReview.objects.create(
            case=case, agrovet=agrovet, round=AgrovetReview.Round.FIRST, chosen_by_farmer=True
        )
        if case.status == Case.Status.DIAGNOSING:
            events.review_assigned(review)
        return review


def assign_pending_reviews() -> int:
    """Periodic: withdraw unanswered reviews and assign every waiting case. Returns reviews created."""
    stale_before = timezone.now() - timedelta(hours=settings.DIAGNOSE["REVIEW_TIMEOUT_HOURS"])
    for review in AgrovetReview.objects.filter(
        status=AgrovetReview.Status.PENDING, created_at__lt=stale_before, case__status__in=REVIEWABLE_STATUSES
    ):
        updated = AgrovetReview.objects.filter(pk=review.pk, status=AgrovetReview.Status.PENDING).update(
            status=AgrovetReview.Status.WITHDRAWN, updated_at=timezone.now()
        )
        if updated:
            logger.warning(
                "Review %s by agrovet %s timed out; reassigning case %s",
                review.id,
                review.agrovet_id,
                review.case_id,
            )

    created = 0
    waiting = Case.objects.filter(status__in=REVIEWABLE_STATUSES).exclude(
        agrovet_reviews__status=AgrovetReview.Status.PENDING
    )
    for case in waiting:
        if assign_review(case) is not None:
            created += 1
    return created


# --- Agrovet access -------------------------------------------------------------------


def get_verified_agrovet(user) -> Agrovet:
    agrovet = getattr(user, "agrovet", None)
    if agrovet is None or not agrovet.is_verified:
        raise DiagnosePermissionDenied("Only verified agrovets can do this.", code="agrovet_not_verified")
    return agrovet


def agrovet_can_view_case(user, case: Case) -> bool:
    agrovet = getattr(user, "agrovet", None)
    if agrovet is None:
        return False
    return (
        case.agrovet_reviews.filter(agrovet=agrovet).exclude(status=AgrovetReview.Status.WITHDRAWN).exists()
    )


def open_reviews_for(agrovet: Agrovet):
    """Pending reviews the agrovet can act on now."""
    return (
        AgrovetReview.objects.filter(
            agrovet=agrovet, status=AgrovetReview.Status.PENDING, case__status__in=REVIEWABLE_STATUSES
        )
        .select_related("case")
        .order_by("created_at")
    )


# --- 3.4 Decision, 3.5 agreement check, 3.6 second opinion ----------------------------


def decide(
    *, agrovet_user, review: AgrovetReview, disease_id=None, unsure: bool = False, notes: str = ""
) -> AgrovetReview:
    """Record the agrovet's decision and move the case on."""
    agrovet = get_verified_agrovet(agrovet_user)
    if bool(disease_id) == bool(unsure):
        raise DiagnoseError("Choose a disease, or mark the case as unsure.", code="invalid_decision")
    disease = None
    if disease_id:
        disease = Disease.objects.filter(pk=disease_id, is_active=True).first()
        if disease is None:
            raise DiagnoseError("Unknown disease.", code="unknown_disease")

    with transaction.atomic():
        review = AgrovetReview.objects.select_for_update().select_related("case").get(pk=review.pk)
        case = Case.objects.select_for_update().get(pk=review.case_id)
        if review.agrovet_id != agrovet.id:
            raise DiagnoseNotFound("Review not found.", code="review_not_found")
        if review.status != AgrovetReview.Status.PENDING:
            raise DiagnoseConflict("This review is closed.", code="review_closed")
        if ROUND_FOR_STATUS.get(case.status) != review.round:
            raise DiagnoseConflict(
                f"This case is {case.status} and cannot be reviewed now.", code="case_not_reviewable"
            )

        evidence = collect_evidence(case)
        review.status = AgrovetReview.Status.DECIDED
        review.decision = AgrovetReview.Decision.UNSURE if unsure else AgrovetReview.Decision.DISEASE
        review.disease = disease
        review.notes = notes
        review.evidence = evidence
        review.decided_at = timezone.now()
        review.save()

        if review.round == AgrovetReview.Round.FIRST:
            _after_first_review(case, review, evidence)
        else:
            _after_second_opinion(case, review, evidence)

    logger.info("Review %s decided: %s %s", review.id, review.decision, review.disease_id or "")
    return review


def _other_opinions(evidence: dict) -> list[str]:
    return [src["opinion"] for src in (evidence["ai"], evidence["similar_cases"]) if src["available"]]


def _after_first_review(case: Case, review: AgrovetReview, evidence: dict) -> None:
    if review.decision == AgrovetReview.Decision.UNSURE:
        _send_to_second_opinion(case, "first agrovet unsure")
        return
    others = _other_opinions(evidence)
    if any(opinion != str(review.disease_id) for opinion in others):
        _send_to_second_opinion(case, f"sources disagree: agrovet={review.disease_id} others={others}")
        return
    confidence = {0: FinalDiagnosis.Confidence.LOW, 1: FinalDiagnosis.Confidence.MEDIUM}.get(
        len(others), FinalDiagnosis.Confidence.HIGH
    )
    _finalize(case, review.disease, confidence, review.agrovet)


def _after_second_opinion(case: Case, review: AgrovetReview, evidence: dict) -> None:
    first = (
        case.agrovet_reviews.filter(round=AgrovetReview.Round.FIRST, status=AgrovetReview.Status.DECIDED)
        .select_related("agrovet")
        .first()
    )
    first_opinion = str(first.disease_id) if first and first.disease_id else None

    if first_opinion and review.disease_id:
        same = first_opinion == str(review.disease_id)
        adjust_trust(
            user=first.agrovet.user,
            reason=TrustEvent.Reason.DIAGNOSIS_CONFIRMED
            if same
            else TrustEvent.Reason.DIAGNOSIS_CONTRADICTED,
            delta=settings.TRUST["DIAGNOSIS_CONFIRMED" if same else "DIAGNOSIS_CONTRADICTED"],
            source_ref=f"case:{case.id}",
        )

    if review.decision == AgrovetReview.Decision.DISEASE:
        supporting = set(_other_opinions(evidence))
        if first_opinion:
            supporting.add(first_opinion)
        if str(review.disease_id) in supporting:
            _finalize(case, review.disease, FinalDiagnosis.Confidence.MEDIUM, review.agrovet)
            return
    transition(case.id, from_statuses=[Case.Status.SECOND_OPINION], to=Case.Status.UNKNOWN)
    events.diagnosis_unknown(case)
    logger.info("Case %s is UNKNOWN: no agreement after second opinion", case.id)


def _send_to_second_opinion(case: Case, why: str) -> None:
    transition(case.id, from_statuses=[Case.Status.DIAGNOSING], to=Case.Status.SECOND_OPINION)
    logger.info("Case %s sent for a second opinion (%s)", case.id, why)
    assign_review_after_commit(case.id)


def _finalize(case: Case, disease: Disease, confidence: str, agrovet: Agrovet) -> FinalDiagnosis:
    final = FinalDiagnosis.objects.create(
        case=case,
        disease=disease,
        confidence=confidence,
        confirmed_by=agrovet,
        ward=case.ward,
        latitude=case.latitude,
        longitude=case.longitude,
    )
    transition(case.id, from_statuses=REVIEWABLE_STATUSES, to=Case.Status.DIAGNOSED)
    events.diagnosis_confirmed(final, ai_corrected=ai_corrected(case, final))
    logger.info("Case %s DIAGNOSED: %s (%s) by %s", case.id, disease.name, confidence, agrovet.id)
    return final
