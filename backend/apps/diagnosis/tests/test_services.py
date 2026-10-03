import io
from datetime import timedelta
from unittest import mock

import pytest
import responses
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from apps.cases.models import Case, CasePhoto
from apps.diagnosis import services
from apps.diagnosis.models import AIDiagnosis

from .conftest import KINDWISE_URL, make_image_bytes

pytestmark = pytest.mark.django_db


def _pending(case):
    return AIDiagnosis.objects.create(case=case, provider="kindwise")


def test_request_creates_pending_run_and_queues_after_commit(
    case_with_photos, django_capture_on_commit_callbacks
):
    with mock.patch("apps.diagnosis.tasks.run_ai_diagnosis_task.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            ai = services.request_ai_diagnosis(case_with_photos)

    assert ai.status == AIDiagnosis.Status.PENDING
    delay.assert_called_once_with(str(ai.id))


def test_request_without_photos_rejected(case):
    with pytest.raises(services.NoPhotosError):
        services.request_ai_diagnosis(case)


def test_only_one_active_run_per_case(case_with_photos):
    services.request_ai_diagnosis(case_with_photos)
    with pytest.raises(services.AIDiagnosisInProgressError):
        services.request_ai_diagnosis(case_with_photos)


@responses.activate
def test_successful_run_stores_top_suggestions_and_advances_case(case_with_photos, kindwise_response):
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = _pending(case_with_photos)

    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.COMPLETED

    ai.refresh_from_db()
    assert ai.status == AIDiagnosis.Status.COMPLETED
    assert ai.attempts == 1
    assert ai.external_ref == "SChIQy84K8bvPtd"
    assert ai.is_plant is True and ai.is_tomato is True and not ai.needs_retake
    assert ai.crop_name == "tomato"
    suggestions = list(ai.suggestions.order_by("rank"))
    assert [s.name for s in suggestions] == ["late blight", "healthy", "early blight"]  # TOP_N = 3
    assert suggestions[1].is_healthy is True
    assert ai.top_suggestion.scientific_name == "Phytophthora infestans"

    case_with_photos.refresh_from_db()
    assert case_with_photos.status == Case.Status.DIAGNOSING

    # All three photos were sent in one identification.
    assert responses.calls[0].request.body.count(b'filename="') == 3


@responses.activate
def test_non_tomato_photo_needs_retake_and_case_stays_reported(case_with_photos, kindwise_response):
    kindwise_response["result"]["crop"]["suggestions"] = [
        {"id": "m1", "name": "maize", "probability": 0.95, "scientific_name": "Zea mays"}
    ]
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = _pending(case_with_photos)

    services.run_ai_diagnosis(ai.id)

    ai.refresh_from_db()
    assert ai.is_tomato is False and ai.needs_retake
    case_with_photos.refresh_from_db()
    assert case_with_photos.status == Case.Status.REPORTED


@responses.activate
def test_not_a_plant_needs_retake(case_with_photos, kindwise_response):
    kindwise_response["result"]["is_plant"] = {"probability": 0.02, "threshold": 0.5, "binary": False}
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = _pending(case_with_photos)

    services.run_ai_diagnosis(ai.id)

    ai.refresh_from_db()
    assert ai.is_plant is False and ai.needs_retake


@responses.activate
@override_settings(DIAGNOSIS={**services.settings.DIAGNOSIS, "MAX_ATTEMPTS": 2})
def test_temporary_errors_retry_then_fail_and_case_still_goes_to_agrovet(case_with_photos):
    responses.post(KINDWISE_URL, body="down", status=503)
    ai = _pending(case_with_photos)

    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.RETRY
    ai.refresh_from_db()
    assert ai.status == AIDiagnosis.Status.PENDING and ai.attempts == 1
    assert ai.error_code == "provider_unavailable"

    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.FAILED
    ai.refresh_from_db()
    assert ai.status == AIDiagnosis.Status.FAILED and ai.attempts == 2
    case_with_photos.refresh_from_db()
    assert case_with_photos.status == Case.Status.DIAGNOSING


@responses.activate
def test_out_of_credits_fails_without_retry(case_with_photos):
    responses.post(KINDWISE_URL, body="no credits", status=429)
    ai = _pending(case_with_photos)

    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.FAILED
    ai.refresh_from_db()
    assert ai.error_code == "provider_quota"


@responses.activate
def test_finished_run_is_skipped_without_calling_provider(case_with_photos):
    ai = _pending(case_with_photos)
    AIDiagnosis.objects.filter(pk=ai.pk).update(status=AIDiagnosis.Status.COMPLETED)

    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.SKIPPED
    assert len(responses.calls) == 0


@responses.activate
def test_fresh_processing_run_is_skipped_but_stale_one_is_reclaimed(case_with_photos, kindwise_response):
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = _pending(case_with_photos)
    AIDiagnosis.objects.filter(pk=ai.pk).update(
        status=AIDiagnosis.Status.PROCESSING, updated_at=timezone.now()
    )
    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.SKIPPED

    AIDiagnosis.objects.filter(pk=ai.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.COMPLETED


def test_unexpected_error_does_not_leave_run_processing(case_with_photos):
    ai = _pending(case_with_photos)
    with mock.patch("apps.diagnosis.services.get_provider", side_effect=RuntimeError("boom")):
        assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.RETRY
    ai.refresh_from_db()
    assert ai.status == AIDiagnosis.Status.PENDING
    assert ai.error_code == "internal_error"


def test_unreadable_photo_fails_permanently(case):
    CasePhoto.objects.create(
        case=case, type=CasePhoto.Type.LEAF, image=SimpleUploadedFile("leaf.jpg", b"not an image")
    )
    ai = _pending(case)
    assert services.run_ai_diagnosis(ai.id) is services.RunOutcome.FAILED
    ai.refresh_from_db()
    assert ai.error_code == "provider_rejected_request"


def test_photos_are_downscaled_before_upload(case):
    CasePhoto.objects.create(
        case=case,
        type=CasePhoto.Type.LEAF,
        image=SimpleUploadedFile("big.png", make_image_bytes(size=(4000, 3000), fmt="PNG")),
    )
    [image] = services._load_images(case)
    width, height = Image.open(io.BytesIO(image.content)).size
    assert max(width, height) == 1600
    assert image.content_type == "image/jpeg"


def test_retry_delay_backs_off_and_caps():
    assert services.retry_delay_seconds(1) == 30
    assert services.retry_delay_seconds(2) == 60
    assert services.retry_delay_seconds(20) == 900


@responses.activate
def test_task_end_to_end(case_with_photos, kindwise_response, django_capture_on_commit_callbacks):
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    with django_capture_on_commit_callbacks(execute=True):
        ai = services.request_ai_diagnosis(case_with_photos)
    ai.refresh_from_db()
    assert ai.status == AIDiagnosis.Status.COMPLETED
