"""Diagnose module, process 3.1: request and record the AI suggestion for a case."""

from __future__ import annotations

import enum
import io
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.cases.models import Case

from .models import AIDiagnosis, AISuggestion
from .providers import get_provider
from .providers.base import IdentificationResult, ImageInput, ProviderError, ProviderRequestError

logger = logging.getLogger(__name__)

TOMATO_NAMES = frozenset({"tomato", "solanum lycopersicum"})

# A PROCESSING run older than this is assumed to belong to a dead worker and may be reclaimed.
# Must exceed CELERY_TASK_TIME_LIMIT.
STALE_PROCESSING_AFTER = timedelta(minutes=5)


class DiagnosisError(Exception):
    pass


class NoPhotosError(DiagnosisError):
    pass


class AIDiagnosisInProgressError(DiagnosisError):
    pass


class InternalDiagnosisError(ProviderError):
    """Unexpected error on our side while running a diagnosis. Retried, then failed."""

    code = "internal_error"
    retryable = True


class RunOutcome(enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


def request_ai_diagnosis(case: Case) -> AIDiagnosis:
    """Create a pending AI run for ``case`` and queue it after the transaction commits."""
    from .tasks import run_ai_diagnosis_task

    if not case.photos.exists():
        raise NoPhotosError("Case has no photos to diagnose")

    try:
        with transaction.atomic():
            ai_diagnosis = AIDiagnosis.objects.create(case=case, provider=settings.DIAGNOSIS["PROVIDER"])
    except IntegrityError as exc:
        raise AIDiagnosisInProgressError("An AI diagnosis is already in progress for this case") from exc

    transaction.on_commit(lambda: run_ai_diagnosis_task.delay(str(ai_diagnosis.id)))
    logger.info("Queued AI diagnosis %s for case %s", ai_diagnosis.id, case.id)
    return ai_diagnosis


def run_ai_diagnosis(ai_diagnosis_id) -> RunOutcome:
    """Call the provider for a pending run and store the result.

    Idempotent: a run that is already finished or being processed elsewhere is
    skipped, so a redelivered task never spends a second provider credit.
    """
    ai_diagnosis = _claim(ai_diagnosis_id)
    if ai_diagnosis is None:
        return RunOutcome.SKIPPED

    case = ai_diagnosis.case
    try:
        images = _load_images(case)
        result = get_provider().identify(
            images,
            latitude=float(case.latitude) if case.latitude is not None else None,
            longitude=float(case.longitude) if case.longitude is not None else None,
            taken_at=case.created_at,
        )
    except ProviderError as exc:
        return _record_failure(ai_diagnosis, exc)
    except Exception as exc:
        # Never leave the run stuck in PROCESSING.
        logger.exception("Unexpected error running AI diagnosis %s", ai_diagnosis.id)
        return _record_failure(ai_diagnosis, InternalDiagnosisError(f"{type(exc).__name__}: {exc}"))

    _record_success(ai_diagnosis, result)
    return RunOutcome.COMPLETED


def retry_delay_seconds(attempts: int) -> int:
    """Exponential backoff: 30s, 60s, 120s, ... capped at 15 minutes."""
    return min(30 * 2 ** max(attempts - 1, 0), 15 * 60)


def _claim(ai_diagnosis_id) -> AIDiagnosis | None:
    stale_before = timezone.now() - STALE_PROCESSING_AFTER
    with transaction.atomic():
        ai_diagnosis = (
            AIDiagnosis.objects.select_for_update().select_related("case").filter(pk=ai_diagnosis_id).first()
        )
        if ai_diagnosis is None:
            logger.warning("AI diagnosis %s no longer exists", ai_diagnosis_id)
            return None
        claimable = ai_diagnosis.status == AIDiagnosis.Status.PENDING or (
            ai_diagnosis.status == AIDiagnosis.Status.PROCESSING and ai_diagnosis.updated_at < stale_before
        )
        if not claimable:
            logger.info("Skipping AI diagnosis %s in status %s", ai_diagnosis.id, ai_diagnosis.status)
            return None
        ai_diagnosis.status = AIDiagnosis.Status.PROCESSING
        ai_diagnosis.attempts += 1
        ai_diagnosis.save(update_fields=["status", "attempts", "updated_at"])
    return ai_diagnosis


def _load_images(case: Case) -> list[ImageInput]:
    max_dimension = settings.DIAGNOSIS["MAX_IMAGE_DIMENSION"]
    images = []
    for photo in case.photos.all():
        try:
            with photo.image.open("rb") as fh:
                img = Image.open(fh)
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                img.thumbnail((max_dimension, max_dimension))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85, optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            raise ProviderRequestError(f"Photo {photo.id} could not be read as an image: {exc}") from exc
        images.append(ImageInput(filename=f"{photo.type}_{photo.id}.jpg", content=buffer.getvalue()))
    if not images:
        raise ProviderRequestError("Case has no photos to diagnose")
    return images


def _record_failure(ai_diagnosis: AIDiagnosis, exc: ProviderError) -> RunOutcome:
    max_attempts = settings.DIAGNOSIS["MAX_ATTEMPTS"]
    will_retry = exc.retryable and ai_diagnosis.attempts < max_attempts

    ai_diagnosis.error_code = exc.code
    ai_diagnosis.error_message = str(exc)[:2000]
    if will_retry:
        ai_diagnosis.status = AIDiagnosis.Status.PENDING
        logger.warning(
            "AI diagnosis %s attempt %s failed (%s); will retry",
            ai_diagnosis.id,
            ai_diagnosis.attempts,
            exc.code,
        )
    else:
        ai_diagnosis.status = AIDiagnosis.Status.FAILED
        ai_diagnosis.completed_at = timezone.now()
        log = logger.error if exc.code in ("provider_auth", "provider_quota") else logger.warning
        log("AI diagnosis %s failed permanently (%s): %s", ai_diagnosis.id, exc.code, exc)

    with transaction.atomic():
        ai_diagnosis.save(
            update_fields=["status", "error_code", "error_message", "completed_at", "updated_at"]
        )
        if not will_retry:
            # The AI only assists: when it cannot help, the case still goes to an agrovet.
            _advance_case_to_diagnosing(ai_diagnosis.case_id, ai_diagnosis)
    return RunOutcome.RETRY if will_retry else RunOutcome.FAILED


def _record_success(ai_diagnosis: AIDiagnosis, result: IdentificationResult) -> None:
    config = settings.DIAGNOSIS
    top_crop = result.crop_suggestions[0] if result.crop_suggestions else None

    ai_diagnosis.status = AIDiagnosis.Status.COMPLETED
    ai_diagnosis.external_ref = result.external_ref
    ai_diagnosis.model_version = result.model_version
    ai_diagnosis.is_plant_probability = result.is_plant_probability
    ai_diagnosis.is_plant = (
        None
        if result.is_plant_probability is None
        else result.is_plant_probability >= config["MIN_IS_PLANT_PROBABILITY"]
    )
    ai_diagnosis.crop_name = top_crop.name if top_crop else ""
    ai_diagnosis.crop_probability = top_crop.probability if top_crop else None
    ai_diagnosis.is_tomato = _is_tomato(result, config["MIN_TOMATO_PROBABILITY"])
    ai_diagnosis.raw_response = result.raw
    ai_diagnosis.error_code = ""
    ai_diagnosis.error_message = ""
    ai_diagnosis.completed_at = timezone.now()

    with transaction.atomic():
        ai_diagnosis.save()
        AISuggestion.objects.bulk_create(
            AISuggestion(
                ai_diagnosis=ai_diagnosis,
                rank=rank,
                external_id=s.external_id,
                name=s.name,
                scientific_name=s.scientific_name,
                probability=s.probability,
                is_healthy=s.is_healthy,
                details=s.details,
                similar_images=s.similar_images,
            )
            for rank, s in enumerate(result.disease_suggestions[: config["TOP_N"]], start=1)
        )
        if ai_diagnosis.needs_retake:
            from apps.cases.services import retake_reason
            from apps.notifications import events

            events.retake_photos(ai_diagnosis.case, retake_reason(ai_diagnosis), ai_diagnosis)
        else:
            _advance_case_to_diagnosing(ai_diagnosis.case_id, ai_diagnosis)

    logger.info(
        "AI diagnosis %s completed: plant=%s tomato=%s top=%s",
        ai_diagnosis.id,
        ai_diagnosis.is_plant,
        ai_diagnosis.is_tomato,
        result.disease_suggestions[0].name if result.disease_suggestions else None,
    )


def _is_tomato(result: IdentificationResult, min_probability) -> bool | None:
    if not result.crop_suggestions:
        return None
    return any(
        (s.name.lower() in TOMATO_NAMES or s.scientific_name.lower() in TOMATO_NAMES)
        and s.probability >= min_probability
        for s in result.crop_suggestions
    )


def _advance_case_to_diagnosing(case_id, ai_diagnosis: AIDiagnosis | None = None) -> None:
    from apps.notifications import events

    from .review import assign_review_after_commit

    # Conditional update: never moves a case backwards if a human has already acted on it.
    moved = Case.objects.filter(pk=case_id, status=Case.Status.REPORTED).update(
        status=Case.Status.DIAGNOSING, updated_at=timezone.now()
    )
    if moved:
        # Process 3.4: hand the case to the farmer's chosen or the nearest verified agrovet.
        assign_review_after_commit(case_id)
        # Tell the farmer straight away: the provisional AI result, or that the case was received.
        events.case_in_review(Case.objects.select_related("farmer").get(pk=case_id), ai_diagnosis)
