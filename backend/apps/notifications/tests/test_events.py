"""Which SMS each module event sends, to whom."""

import copy
from decimal import Decimal
from unittest import mock

import pytest
import responses
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.accounts.models import Farm, FarmerProfile, User
from apps.cases.models import Case, CasePhoto
from apps.diagnosis import review, services
from apps.diagnosis.models import AgrovetReview, AIDiagnosis
from apps.diagnosis.tests.conftest import KINDWISE_RESPONSE, KINDWISE_URL, make_image_bytes
from apps.diagnosis.tests.test_review import add_ai, make_agrovet, make_case, make_farmer
from apps.notifications.models import SmsMessage
from apps.prescriptions.services import approve
from apps.products.models import Disease, Product, TreatmentRule

pytestmark = pytest.mark.django_db

FARMER_PHONE = "+254700000001"


@pytest.fixture(autouse=True)
def sms_enabled():
    with (
        override_settings(SMS={**settings.SMS, "ENABLED": True}),
        mock.patch("apps.notifications.tasks.send_sms_task.delay"),
    ):
        yield


@pytest.fixture
def farmer(db):
    farmer = make_farmer(FARMER_PHONE)
    FarmerProfile.objects.filter(user=farmer).update(language="en")
    return farmer


@pytest.fixture
def agrovet(db):
    agrovet = make_agrovet("near", "-0.330000", "37.658000")
    agrovet.phone = "0722000111"
    agrovet.save()
    return agrovet


@pytest.fixture
def late_blight(db):
    return Disease.objects.create(name="Late blight")


@pytest.fixture
def kindwise_response():
    return copy.deepcopy(KINDWISE_RESPONSE)


@pytest.fixture
def case_with_photos(farmer):
    case = make_case(farmer, status=Case.Status.REPORTED)
    for photo_type in CasePhoto.REQUIRED_TYPES:
        CasePhoto.objects.create(
            case=case,
            type=photo_type,
            image=SimpleUploadedFile(f"{photo_type}.jpg", make_image_bytes(), content_type="image/jpeg"),
        )
    return case


def sms(purpose, to=None):
    qs = SmsMessage.objects.filter(purpose=purpose)
    if to:
        qs = qs.filter(to=to)
    return list(qs)


def run_ai(case, kindwise_response, capture):
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = AIDiagnosis.objects.create(case=case, provider="kindwise")
    with capture(execute=True):
        services.run_ai_diagnosis(ai.id)
    return ai


@responses.activate
def test_ai_result_goes_to_farmer_and_case_to_agrovet(
    farmer, agrovet, late_blight, case_with_photos, kindwise_response, django_capture_on_commit_callbacks
):

    run_ai(case_with_photos, kindwise_response, django_capture_on_commit_callbacks)

    [to_farmer] = sms("ai_result")
    assert to_farmer.to == FARMER_PHONE
    assert to_farmer.body.startswith("AgriSense: Likely Late blight (98%), not yet confirmed.")
    [to_agrovet] = sms("review_assigned")
    assert to_agrovet.to == "+254722000111"
    assert "New tomato case to review in Chuka (first review)" in to_agrovet.body


@responses.activate
def test_non_tomato_photos_ask_farmer_to_retake(
    farmer, agrovet, case_with_photos, kindwise_response, django_capture_on_commit_callbacks
):
    kindwise_response["result"]["crop"]["suggestions"] = [
        {"id": "p1", "name": "potato", "probability": 0.95, "scientific_name": "Solanum tuberosum"}
    ]

    run_ai(case_with_photos, kindwise_response, django_capture_on_commit_callbacks)

    [retake] = sms("retake_photos")
    assert "do not look like tomato" in retake.body
    assert not sms("ai_result") and not sms("review_assigned")


@override_settings(DIAGNOSIS={**settings.DIAGNOSIS, "MAX_ATTEMPTS": 1})
@responses.activate
def test_ai_failure_still_tells_farmer_the_report_was_received(
    farmer, agrovet, case_with_photos, django_capture_on_commit_callbacks
):
    responses.post(KINDWISE_URL, status=500)
    ai = AIDiagnosis.objects.create(case=case_with_photos, provider="kindwise")

    with django_capture_on_commit_callbacks(execute=True):
        services.run_ai_diagnosis(ai.id)

    [received] = sms("ai_result")
    assert received.body.startswith("AgriSense: We received your report.")


def test_agrovet_chosen_before_ai_finishes_is_told_once_case_is_reviewable(farmer, agrovet):
    case = make_case(farmer, status=Case.Status.REPORTED)
    review.choose_agrovet(farmer=farmer, case=case, agrovet_id=agrovet.id)
    assert not sms("review_assigned")  # nothing to review yet

    Case.objects.filter(pk=case.pk).update(status=Case.Status.DIAGNOSING)
    review.assign_review(case)
    review.assign_review(case)  # periodic task again: no duplicate

    assert len(sms("review_assigned", to="+254722000111")) == 1


def test_confirmation_and_correction_messages(farmer, agrovet, late_blight):
    case = make_case(farmer)
    add_ai(case, "late blight")
    review.decide(
        agrovet_user=agrovet.user,
        review=AgrovetReview.objects.create(case=case, agrovet=agrovet, round=1),
        disease_id=late_blight.id,
    )
    [confirmed] = sms("diagnosis_confirmed")
    assert confirmed.body == (
        "AgriSense: Confirmed by near: Late blight. Your agrovet is preparing a prescription."
    )

    other_case = make_case(farmer)
    add_ai(other_case, "healthy", healthy=True, probability="0.3000")  # too unsure to force a second opinion
    review.decide(
        agrovet_user=agrovet.user,
        review=AgrovetReview.objects.create(case=other_case, agrovet=agrovet, round=1),
        disease_id=late_blight.id,
    )
    corrected = SmsMessage.objects.get(purpose="diagnosis_confirmed", source_ref=f"case:{other_case.id}")
    assert "differs from the computer suggestion" in corrected.body


def test_unknown_outcome_sends_plant_clinic_advice(farmer, agrovet, late_blight):
    second = make_agrovet("far", "-0.240000", "37.640000")
    case = make_case(farmer, status=Case.Status.SECOND_OPINION)
    review.decide(
        agrovet_user=second.user,
        review=AgrovetReview.objects.create(case=case, agrovet=second, round=2),
        unsure=True,
    )
    [unknown] = sms("diagnosis_unknown")
    assert "plant clinic" in unknown.body


def test_prescription_code_is_sent_by_sms(farmer, agrovet, late_blight):
    TreatmentRule.objects.create(disease=late_blight, active_ingredient="mancozeb")
    product = Product.objects.create(
        pcpb_reg_no="PCPB (CR) 0856",
        name="Ridomil Gold MZ 68 WG",
        active_ingredients=["mancozeb"],
        approved_crops=["tomato"],
        rate_per_acre=Decimal("250"),
        rate_unit="g",
        pack_size=Decimal("250"),
    )
    farm = Farm.objects.create(farmer=farmer, latitude="-0.33", longitude="37.65", size_acres="0.50")
    case = make_case(farmer)
    Case.objects.filter(pk=case.pk).update(farm=farm)
    add_ai(case, "late blight")
    review.decide(
        agrovet_user=agrovet.user,
        review=AgrovetReview.objects.create(case=case, agrovet=agrovet, round=1),
        disease_id=late_blight.id,
    )

    prescription = approve(agrovet_user=agrovet.user, case=case, product_id=product.id)

    [message] = sms("prescription_issued")
    assert message.body.startswith(
        f"AgriSense prescription {prescription.code}: Ridomil Gold MZ 68 WG, 1 x 250 g."
    )
    assert "Show this code at a verified agrovet." in message.body


def test_farmer_without_phone_is_skipped(agrovet, late_blight):
    user = User.objects.create_user(username="nophone", password="x")
    case = make_case(user)
    review.decide(
        agrovet_user=agrovet.user,
        review=AgrovetReview.objects.create(case=case, agrovet=agrovet, round=1),
        disease_id=late_blight.id,
    )
    case.refresh_from_db()
    assert case.status == Case.Status.DIAGNOSED
    assert not sms("diagnosis_confirmed")
