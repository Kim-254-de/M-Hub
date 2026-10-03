"""Apply and Follow-up: spraying, day 2/4/7 check-ins, outcomes and expected results."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import FarmerProfile, User
from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.diagnosis.models import FinalDiagnosis
from apps.diagnosis.tests.conftest import make_image_bytes
from apps.followups import services
from apps.followups.models import SprayRecord
from apps.prescriptions.models import Prescription, TreatmentOutcome
from apps.prescriptions.services import local_results
from apps.products.models import Disease, Product
from apps.purchases.models import Order, Verification
from apps.rewards.services import balance

pytestmark = pytest.mark.django_db

LAT, LNG = "-0.333000", "37.650000"


def client_for(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def farmer(db):
    user = User.objects.create_user(username="farmer", password="x", phone="+254700000001")
    FarmerProfile.objects.create(
        user=user, language="en", county="Tharaka Nithi", ward="Chuka", consent_at=timezone.now()
    )
    return user


@pytest.fixture
def agrovet(db):
    user = User.objects.create_user(username="agro", password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user, name="Chuka Agrovet", pcpb_licence_no="L1", latitude=LAT, longitude=LNG, status="verified"
    )


@pytest.fixture
def late_blight(db):
    return Disease.objects.create(name="Late blight")


@pytest.fixture
def product(db):
    return Product.objects.create(pcpb_reg_no="PCPB (CR) 0856", name="Ridomil Gold MZ 68 WG", phi_days=7)


def verified_case(farmer, agrovet, disease, product, *, collected_days_ago=10, ward="Chuka"):
    """A case through Diagnose, Prescribe and Buy with a verified label check."""
    case = Case.objects.create(
        farmer=farmer,
        status=Case.Status.VERIFIED,
        ward=ward,
        latitude=LAT,
        longitude=LNG,
        symptom_answers={"share_affected": "some"},
    )
    FinalDiagnosis.objects.create(
        case=case, disease=disease, confidence="medium", confirmed_by=agrovet, ward=ward
    )
    prescription = Prescription.objects.create(
        case=case,
        approved_product=product,
        approved_by=agrovet,
        disease=disease,
        expires_at=timezone.now() + timedelta(days=14),
    )
    order = Order.objects.create(
        prescription=prescription,
        farmer=farmer,
        agrovet=agrovet,
        product=product,
        unit_price_kes=650,
        quantity=1,
        total_kes=650,
        payment_method="pay_at_shop",
        status=Order.Status.COLLECTED,
        collected_at=timezone.now() - timedelta(days=collected_days_ago),
    )
    Verification.objects.create(
        order=order, type="label_check", result="verified", actor=farmer, product=product
    )
    return case


@pytest.fixture
def case(farmer, agrovet, late_blight, product):
    return verified_case(farmer, agrovet, late_blight, product)


def sprayed(farmer, case, days_ago):
    return services.record_spray(
        farmer=farmer, case=case, sprayed_at=timezone.now() - timedelta(days=days_ago)
    )


def check_in(farmer, case, day, new_spots="stopped", share="few"):
    return services.add_check_in(farmer=farmer, case=case, day=day, new_spots=new_spots, share_affected=share)


# --- Spraying -----------------------------------------------------------------------------


def test_follow_up_only_after_a_verified_purchase(farmer, agrovet, late_blight, product):
    case = verified_case(farmer, agrovet, late_blight, product)
    Case.objects.filter(pk=case.pk).update(status=Case.Status.PURCHASED)
    case.refresh_from_db()
    with pytest.raises(services.FollowUpConflict) as exc:
        services.record_spray(farmer=farmer, case=case)
    assert exc.value.code == "not_verified"

    stranger = User.objects.create_user(username="stranger", password="x")
    with pytest.raises(services.FollowUpNotFound):
        services.record_spray(farmer=stranger, case=case)


def test_spray_date_must_be_after_collection_and_not_in_future(farmer, case):
    with pytest.raises(services.FollowUpError) as exc:
        sprayed(farmer, case, days_ago=-1)
    assert exc.value.code == "future_date"
    with pytest.raises(services.FollowUpError) as exc:
        sprayed(farmer, case, days_ago=11)  # collected 10 days ago
    assert exc.value.code == "before_purchase"


def test_spray_starts_the_schedule(farmer, case, late_blight, product):
    record = sprayed(farmer, case, days_ago=0)

    assert (record.product, record.disease, record.baseline_share_affected) == (product, late_blight, "some")
    assert [i["status"] for i in services.schedule(record)] == ["upcoming", "upcoming", "upcoming"]
    assert services.harvest_safe_from(record) == record.sprayed_at + timedelta(days=7)
    with pytest.raises(services.FollowUpConflict):
        services.record_spray(farmer=farmer, case=case)


# --- Check-ins ---------------------------------------------------------------------------------


def test_check_in_rules(farmer, case):
    with pytest.raises(services.FollowUpConflict):
        check_in(farmer, case, 2)  # not sprayed yet

    sprayed(farmer, case, days_ago=3)
    with pytest.raises(services.FollowUpConflict) as exc:
        check_in(farmer, case, 4)
    assert exc.value.code == "too_early"
    with pytest.raises(services.FollowUpError) as exc:
        check_in(farmer, case, 3)
    assert exc.value.code == "invalid_day"

    check_in(farmer, case, 2, new_spots="fewer", share="some")
    with pytest.raises(services.FollowUpConflict) as exc:
        check_in(farmer, case, 2)
    assert exc.value.code == "already_checked_in"


def test_final_check_in_becomes_the_outcome_and_earns_points(farmer, case, late_blight, product):
    record = sprayed(farmer, case, days_ago=8)
    check_in(farmer, case, 2, new_spots="fewer", share="some")
    check_in(farmer, case, 4, new_spots="stopped", share="some")
    check_in(farmer, case, 7, new_spots="stopped", share="few")

    outcome = TreatmentOutcome.objects.get(case=case)
    assert (outcome.disease, outcome.product, outcome.improved) == (late_blight, product, True)
    assert outcome.days_after_spraying == 4  # first day the spread had stopped
    assert outcome.ward == "Chuka"
    record.refresh_from_db()
    assert record.completed_at is not None
    assert balance(farmer) == 5
    with pytest.raises(services.FollowUpConflict) as exc:
        check_in(farmer, case, 4)
    assert exc.value.code == "follow_up_closed"


def test_still_spreading_or_worse_than_reported_is_not_improved(farmer, agrovet, late_blight, product):
    spreading = verified_case(farmer, agrovet, late_blight, product)
    sprayed(farmer, spreading, days_ago=8)
    check_in(farmer, spreading, 7, new_spots="spreading", share="some")
    assert TreatmentOutcome.objects.get(case=spreading).improved is False

    worse = verified_case(farmer, agrovet, late_blight, product)
    sprayed(farmer, worse, days_ago=8)
    check_in(farmer, worse, 7, new_spots="stopped", share="most")  # reported "some"
    outcome = TreatmentOutcome.objects.get(case=worse)
    assert outcome.improved is False and outcome.days_after_spraying is None


def test_follow_up_closes_after_two_weeks(farmer, case):
    record = sprayed(farmer, case, days_ago=9)
    SprayRecord.objects.filter(pk=record.pk).update(sprayed_at=timezone.now() - timedelta(days=15))
    record.refresh_from_db()

    assert [i["status"] for i in services.schedule(record)] == ["missed", "missed", "missed"]
    with pytest.raises(services.FollowUpConflict):
        check_in(farmer, case, 7)
    assert not TreatmentOutcome.objects.exists()


def test_completed_follow_up_feeds_prescribe_ranking(farmer, case, late_blight, product):
    sprayed(farmer, case, days_ago=8)
    check_in(farmer, case, 7)
    result = local_results(case, late_blight, [product])[product.id]
    assert (result.improved, result.reported, result.typical_day) == (1, 1, 7)


# --- Expected results ---------------------------------------------------------------------------


def test_expected_results_from_verified_farmers_nearby(farmer, agrovet, case, late_blight, product):
    for i, (stopped_day, share) in enumerate(
        [(2, "few"), (4, "few"), (4, "few"), (4, "some"), (None, "most")]
    ):
        neighbour = User.objects.create_user(username=f"n{i}", password="x")
        other = verified_case(neighbour, agrovet, late_blight, product, collected_days_ago=30)
        services.record_spray(farmer=neighbour, case=other, sprayed_at=timezone.now() - timedelta(days=25))
        SprayRecord.objects.filter(case=other).update(sprayed_at=timezone.now() - timedelta(days=8))
        if stopped_day and stopped_day < 7:
            check_in(neighbour, other, stopped_day)
        check_in(neighbour, other, 7, new_spots="stopped" if stopped_day else "spreading", share=share)
        SprayRecord.objects.filter(case=other).update(sprayed_at=timezone.now() - timedelta(days=25))
    # One neighbour sprayed long ago and never reported back.
    silent = User.objects.create_user(username="silent", password="x")
    silent_case = verified_case(silent, agrovet, late_blight, product, collected_days_ago=30)
    services.record_spray(farmer=silent, case=silent_case, sprayed_at=timezone.now() - timedelta(days=25))

    expected = services.expected_results(case, late_blight, product)

    assert expected["text"] == "4 of 5 verified farmers nearby saw the spread stop, usually by day 4"
    assert (expected["improved"], expected["reported"], expected["typical_day"]) == (4, 5, 4)
    assert expected["response_rate"] == 0.83  # 5 of 6 finished


def test_expected_results_need_minimum_reports(farmer, case, late_blight, product):
    expected = services.expected_results(case, late_blight, product)
    assert expected["text"] == "Not enough local data yet"
    assert expected["improved"] is None and expected["response_rate"] is None


# --- API -----------------------------------------------------------------------------------------


def test_follow_up_api_flow(farmer, case):
    api = client_for(farmer)
    url = reverse("v1:case-follow-up", kwargs={"case_id": case.id})

    before = api.get(url).data
    assert before["can_record_spray"] is True and before["spray"] is None
    assert before["expected"]["product"] == "Ridomil Gold MZ 68 WG"

    sprayed_at = (timezone.now() - timedelta(days=4, hours=1)).isoformat()
    created = api.post(
        reverse("v1:case-follow-up-spray", kwargs={"case_id": case.id}),
        {"sprayed_at": sprayed_at, "amount_used": "Half the pack"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["can_record_spray"] is False
    assert created.data["spray"]["harvest_safe_from"] is not None
    assert [i["status"] for i in created.data["schedule"]] == ["due", "due", "upcoming"]
    assert created.data["next_due_day"] == 2

    photo = SimpleUploadedFile("day2.jpg", make_image_bytes(), content_type="image/jpeg")
    checked = api.post(
        reverse("v1:case-follow-up-check-ins", kwargs={"case_id": case.id}),
        {"day": 2, "new_spots": "fewer", "share_affected": "some", "photo": photo},
        format="multipart",
    )
    assert checked.status_code == 201, checked.data
    day2 = checked.data["schedule"][0]["check_in"]
    assert day2["photo"]
    assert day2["advice"] == (
        "Some new spots are still appearing. Keep removing spotted leaves and check your crop again on day 4."
    )

    spreading = api.post(
        reverse("v1:case-follow-up-check-ins", kwargs={"case_id": case.id}),
        {"day": 4, "new_spots": "spreading", "share_affected": "most"},
        format="json",
    )
    assert spreading.data["schedule"][1]["check_in"]["advice"].startswith("The spread has not stopped.")

    early = api.post(
        reverse("v1:case-follow-up-check-ins", kwargs={"case_id": case.id}),
        {"day": 7, "new_spots": "stopped", "share_affected": "few"},
        format="json",
    )
    assert early.status_code == 409 and early.data["code"] == "too_early"


def test_follow_up_api_is_for_the_cases_farmer_only(farmer, agrovet, case):
    url = reverse("v1:case-follow-up", kwargs={"case_id": case.id})
    assert client_for(User.objects.create_user(username="other", password="x")).get(url).status_code == 404
    assert client_for(agrovet.user).get(url).status_code == 403


def test_swahili_advice(farmer, case):
    FarmerProfile.objects.filter(user=farmer).update(language="sw")
    sprayed(farmer, case, days_ago=3)
    check_in(farmer, case, 2, new_spots="stopped", share="few")

    data = client_for(farmer).get(reverse("v1:case-follow-up", kwargs={"case_id": case.id})).data

    assert (
        data["schedule"][0]["check_in"]["advice"]
        == "Vizuri: hakuna madoa mapya. Kagua zao lako tena siku ya 4."
    )


def test_points_are_not_awarded_twice(farmer, case):
    sprayed(farmer, case, days_ago=8)
    check_in(farmer, case, 7)
    services._complete(SprayRecord.objects.get(case=case))
    assert balance(farmer) == Decimal(5)
