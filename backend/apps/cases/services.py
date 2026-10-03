"""Detect module (Documentation §6.1, process 2.0): capture a report and hand it to Diagnose.

Flow: start a DRAFT case -> add the three guided photos (checked locally on
upload) -> answer the quick questions -> submit. Submitting marks the case
REPORTED and queues the AI diagnosis run, which also checks that the photos
show a tomato plant. If that check fails, the farmer retakes photos and
submits again.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Farm, FarmerProfile, User
from apps.diagnosis import services as diagnosis_services
from apps.diagnosis.models import AIDiagnosis

from .models import Case, CasePhoto
from .quality import assess_photo

logger = logging.getLogger(__name__)


class DetectError(Exception):
    code = "detect_error"


class CaseNotEditableError(DetectError):
    code = "case_not_editable"


class IncompleteCaseError(DetectError):
    code = "case_incomplete"


def farmer_language(user: User) -> str:
    profile = FarmerProfile.objects.filter(user=user).only("language").first()
    return profile.language if profile else FarmerProfile.Language.ENGLISH


def latest_ai_diagnosis(case: Case) -> AIDiagnosis | None:
    return AIDiagnosis.objects.filter(case=case).order_by("-created_at").first()


def retake_reason(ai_diagnosis: AIDiagnosis | None) -> str | None:
    """Why the AI run asked for new photos, or None if it did not."""
    if ai_diagnosis is None or not ai_diagnosis.needs_retake:
        return None
    return "not_plant" if ai_diagnosis.is_plant is False else "not_tomato"


def is_editable(case: Case) -> bool:
    """Photos and answers can change while drafting, or after the AI asked for a retake."""
    if case.status == Case.Status.DRAFT:
        return True
    return case.status == Case.Status.REPORTED and retake_reason(latest_ai_diagnosis(case)) is not None


def start_case(
    farmer: User,
    *,
    farm: Farm | None = None,
    channel: str = Case.Channel.APP,
    latitude=None,
    longitude=None,
) -> Case:
    if farm is not None and farm.farmer_id != farmer.id:
        raise DetectError("Farm does not belong to this farmer")
    return Case.objects.create(
        farmer=farmer,
        farm=farm,
        channel=channel,
        status=Case.Status.DRAFT,
        latitude=latitude,
        longitude=longitude,
    )


def add_photo(case: Case, photo_type: str, image) -> CasePhoto:
    """Check a photo and attach it to the case, replacing any earlier photo of the same type.

    Raises cases.quality.PhotoQualityError when the farmer should retake it.
    """
    quality = assess_photo(image)

    with transaction.atomic():
        case = _lock_editable(case.pk)
        old = CasePhoto.objects.filter(case=case, type=photo_type).first()
        if old is not None:
            old_file = old.image
            old.delete()
            transaction.on_commit(lambda: old_file.storage.delete(old_file.name))
        photo = CasePhoto.objects.create(
            case=case,
            type=photo_type,
            image=image,
            width=quality.width,
            height=quality.height,
            sharpness=quality.sharpness,
            brightness=quality.brightness,
        )
    return photo


def save_answers(case: Case, answers: dict) -> Case:
    with transaction.atomic():
        case = _lock_editable(case.pk)
        case.symptom_answers = answers
        case.save(update_fields=["symptom_answers", "updated_at"])
    return case


def submit_case(case: Case) -> AIDiagnosis:
    """Mark the case REPORTED and queue the AI diagnosis run (Diagnose, process 3.1)."""
    with transaction.atomic():
        case = _lock_editable(case.pk)

        present = set(case.photos.values_list("type", flat=True))
        missing = [t for t in CasePhoto.REQUIRED_TYPES if t not in present]
        if missing:
            raise IncompleteCaseError(f"Missing photos: {', '.join(missing)}")
        if not case.symptom_answers:
            raise IncompleteCaseError("Answer the quick questions before submitting")

        if case.latitude is None and case.farm_id is not None:
            case.latitude, case.longitude = case.farm.latitude, case.farm.longitude
        profile = FarmerProfile.objects.filter(user_id=case.farmer_id).first()
        if profile is not None:
            case.county, case.ward = profile.county, profile.ward
        # A resubmission after a retake keeps the original report time.
        case.submitted_at = case.submitted_at or timezone.now()
        case.status = Case.Status.REPORTED
        case.save(
            update_fields=["latitude", "longitude", "county", "ward", "submitted_at", "status", "updated_at"]
        )

        ai_diagnosis = diagnosis_services.request_ai_diagnosis(case)

    logger.info("Case %s reported; AI diagnosis %s queued", case.id, ai_diagnosis.id)
    return ai_diagnosis


def _lock_editable(case_id) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if not is_editable(case):
        raise CaseNotEditableError(f"Case is {case.status} and can no longer be changed")
    return case
