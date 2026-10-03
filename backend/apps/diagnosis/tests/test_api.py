from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.diagnosis.models import AIDiagnosis, AISuggestion

pytestmark = pytest.mark.django_db


def url(case):
    return reverse("v1:case-ai-diagnosis", kwargs={"case_id": case.id})


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def completed_run(case, **kwargs):
    ai = AIDiagnosis.objects.create(
        case=case,
        provider="kindwise",
        status=AIDiagnosis.Status.COMPLETED,
        is_plant=True,
        is_tomato=True,
        **kwargs,
    )
    AISuggestion.objects.create(
        ai_diagnosis=ai,
        rank=1,
        external_id="b9ec757fefb92520",
        name="late blight",
        scientific_name="Phytophthora infestans",
        probability=Decimal("0.9806"),
        details={
            "description": "Destructive.",
            "eppo_code": "PHYTIN",
            "treatment": {"prevention": ["Monitor fields."], "chemical treatment": ["Apply Ridomil Gold."]},
        },
    )
    return ai


@pytest.fixture(autouse=True)
def no_task_dispatch():
    with mock.patch("apps.diagnosis.tasks.run_ai_diagnosis_task.delay") as delay:
        yield delay


def test_requires_authentication(case):
    assert APIClient().get(url(case)).status_code == 403


def test_other_farmer_cannot_see_case(case, other_farmer):
    assert client_for(other_farmer).get(url(case)).status_code == 403


def test_get_returns_404_when_none_requested(case, farmer):
    assert client_for(farmer).get(url(case)).status_code == 404


def test_get_returns_latest_with_safe_details_only(case, farmer):
    completed_run(case)
    response = client_for(farmer).get(url(case))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["needs_retake"] is False
    [suggestion] = body["suggestions"]
    assert suggestion["name"] == "late blight"
    assert suggestion["probability"] == "0.9806"
    details = suggestion["details"]
    assert details["prevention"] == ["Monitor fields."]
    assert details["description"] == "Destructive."
    # Unregistered product advice from the provider must never reach farmers.
    assert "treatment" not in details
    assert "Ridomil" not in response.content.decode()


def test_post_queues_run(case_with_photos, farmer, django_capture_on_commit_callbacks, no_task_dispatch):
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(farmer).post(url(case_with_photos))

    assert response.status_code == 202
    assert response.json()["status"] == "PENDING"
    no_task_dispatch.assert_called_once()


def test_post_without_photos_is_400(case, farmer):
    assert client_for(farmer).post(url(case)).status_code == 400


def test_post_while_in_progress_is_409(case_with_photos, farmer):
    AIDiagnosis.objects.create(case=case_with_photos, provider="kindwise")
    assert client_for(farmer).post(url(case_with_photos)).status_code == 409


def test_farmer_cannot_rerun_completed_diagnosis_but_staff_can(case_with_photos, farmer, staff):
    completed_run(case_with_photos)
    assert client_for(farmer).post(url(case_with_photos)).status_code == 409
    assert client_for(staff).post(url(case_with_photos)).status_code == 202


def test_farmer_can_rerun_after_retake_request(case_with_photos, farmer):
    run = completed_run(case_with_photos)
    AIDiagnosis.objects.filter(pk=run.pk).update(is_tomato=False)
    assert client_for(farmer).post(url(case_with_photos)).status_code == 202


def test_farmer_can_rerun_after_failure(case_with_photos, farmer):
    AIDiagnosis.objects.create(case=case_with_photos, provider="kindwise", status=AIDiagnosis.Status.FAILED)
    assert client_for(farmer).post(url(case_with_photos)).status_code == 202
