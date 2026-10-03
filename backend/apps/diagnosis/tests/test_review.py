"""Diagnose processes 3.2-3.6: evidence, agrovet confirmation, agreement check, second opinion."""

from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import FarmerProfile, User
from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.diagnosis import review, services
from apps.diagnosis.models import AgrovetReview, AIDiagnosis, AISuggestion, FinalDiagnosis
from apps.products.models import Disease
from apps.rewards.models import TrustEvent

from .conftest import KINDWISE_URL

pytestmark = pytest.mark.django_db

# Chuka, Tharaka Nithi
LAT, LNG = "-0.333000", "37.650000"


def client_for(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def make_farmer(phone, ward="Chuka"):
    user = User.objects.create_user(username=phone, password="x", phone=phone)
    FarmerProfile.objects.create(user=user, county="Tharaka Nithi", ward=ward, consent_at=timezone.now())
    return user


def make_agrovet(username, lat, lng, status=Agrovet.Status.VERIFIED):
    user = User.objects.create_user(username=username, password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user,
        name=username,
        pcpb_licence_no=f"LIC-{username}",
        latitude=lat,
        longitude=lng,
        status=status,
    )


def make_case(farmer, status=Case.Status.DIAGNOSING, ward="Chuka", lat=LAT, lng=LNG):
    return Case.objects.create(
        farmer=farmer, status=status, ward=ward, latitude=lat, longitude=lng, submitted_at=timezone.now()
    )


def add_ai(case, name="late blight", probability="0.9200", healthy=False):
    ai = AIDiagnosis.objects.create(
        case=case, provider="kindwise", status=AIDiagnosis.Status.COMPLETED, is_plant=True, is_tomato=True
    )
    AISuggestion.objects.create(
        ai_diagnosis=ai,
        rank=1,
        external_id=f"id-{name}",
        name=name,
        probability=probability,
        is_healthy=healthy,
    )
    return ai


def confirmed_nearby(disease, n, agrovet, ward="Chuka"):
    """n past confirmed cases of ``disease`` in the ward."""
    other = make_farmer(f"+2547{FinalDiagnosis.objects.count():08d}", ward=ward)
    for _ in range(n):
        case = make_case(other, status=Case.Status.DIAGNOSED, ward=ward)
        FinalDiagnosis.objects.create(
            case=case, disease=disease, confidence="high", confirmed_by=agrovet, ward=ward
        )


@pytest.fixture
def farmer(db):
    return make_farmer("+254700000001")


@pytest.fixture
def late_blight(db):
    return Disease.objects.create(name="Late blight", scientific_name="Phytophthora infestans")


@pytest.fixture
def early_blight(db):
    return Disease.objects.create(name="Early blight", scientific_name="Alternaria solani")


@pytest.fixture
def near(db):
    return make_agrovet("near", "-0.330000", "37.658000")  # ~1 km


@pytest.fixture
def far(db):
    return make_agrovet("far", "-0.240000", "37.640000")  # ~10 km


@pytest.fixture
def case(farmer):
    return make_case(farmer)


def first_review(case, agrovet):
    return AgrovetReview.objects.create(case=case, agrovet=agrovet, round=AgrovetReview.Round.FIRST)


# --- 3.1 -> 3.4: assignment -------------------------------------------------------


@responses.activate
def test_ai_success_assigns_nearest_verified_agrovet(
    case_with_photos, kindwise_response, near, far, django_capture_on_commit_callbacks
):
    make_agrovet("pending", "-0.333100", "37.650100", status=Agrovet.Status.PENDING)  # closest, not verified
    Case.objects.filter(pk=case_with_photos.pk).update(status=Case.Status.REPORTED)
    responses.post(KINDWISE_URL, json=kindwise_response, status=201)
    ai = AIDiagnosis.objects.create(case=case_with_photos, provider="kindwise")

    with django_capture_on_commit_callbacks(execute=True):
        services.run_ai_diagnosis(ai.id)

    case_with_photos.refresh_from_db()
    assert case_with_photos.status == Case.Status.DIAGNOSING
    assigned = AgrovetReview.objects.get(case=case_with_photos)
    assert (assigned.agrovet, assigned.round, assigned.status) == (near, 1, "pending")


def test_farmer_choice_made_before_ai_finishes_is_kept(farmer, near, far):
    case = make_case(farmer, status=Case.Status.REPORTED)
    review.choose_agrovet(farmer=farmer, case=case, agrovet_id=far.id)

    Case.objects.filter(pk=case.pk).update(status=Case.Status.DIAGNOSING)
    assert review.assign_review(case) is None  # already has the farmer's pick

    pending = AgrovetReview.objects.get(case=case, status="pending")
    assert pending.agrovet == far and pending.chosen_by_farmer


def test_farmer_can_switch_agrovet_until_reviewed(farmer, case, near, far, late_blight):
    first_review(case, near)
    review.choose_agrovet(farmer=farmer, case=case, agrovet_id=far.id)
    assert AgrovetReview.objects.get(case=case, agrovet=near).status == "withdrawn"

    pending = AgrovetReview.objects.get(case=case, status="pending")
    review.decide(agrovet_user=far.user, review=pending, disease_id=late_blight.id)
    with pytest.raises(review.DiagnoseConflict):
        review.choose_agrovet(farmer=farmer, case=case, agrovet_id=near.id)


def test_unanswered_review_times_out_and_moves_to_next_agrovet(case, near, far):
    stale = first_review(case, near)
    AgrovetReview.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(hours=25))

    assert review.assign_pending_reviews() == 1

    stale.refresh_from_db()
    assert stale.status == "withdrawn"
    assert AgrovetReview.objects.get(case=case, status="pending").agrovet == far


def test_periodic_task_assigns_cases_that_had_no_agrovet(case):
    assert review.assign_pending_reviews() == 0  # nobody verified yet
    agrovet = make_agrovet("late-joiner", LAT, LNG)
    assert review.assign_pending_reviews() == 1
    assert AgrovetReview.objects.get(case=case).agrovet == agrovet


# --- 3.4 / 3.5: decision and agreement check ------------------------------------------


def test_agrovet_agreeing_with_ai_diagnoses_case(case, near, late_blight):
    add_ai(case, "late blight")
    pending = first_review(case, near)

    review.decide(agrovet_user=near.user, review=pending, disease_id=late_blight.id, notes="Classic lesions")

    case.refresh_from_db()
    assert case.status == Case.Status.DIAGNOSED
    final = case.final_diagnosis
    assert (final.disease, final.confidence, final.confirmed_by) == (late_blight, "medium", near)
    pending.refresh_from_db()
    assert pending.evidence["ai"]["opinion"] == str(late_blight.id)


def test_ai_history_and_agrovet_agreeing_is_high_confidence(case, near, far, late_blight):
    add_ai(case, "Phytophthora infestans")  # matched by scientific name
    confirmed_nearby(late_blight, 3, far)
    pending = first_review(case, near)

    review.decide(agrovet_user=near.user, review=pending, disease_id=late_blight.id)

    case.refresh_from_db()
    pending.refresh_from_db()
    assert case.final_diagnosis.confidence == "high"
    assert pending.evidence["similar_cases"]["total"] == 3


def test_agrovet_alone_is_low_confidence(case, near, early_blight):
    add_ai(case, "late blight", probability="0.3000")  # too unsure to count
    pending = first_review(case, near)

    review.decide(agrovet_user=near.user, review=pending, disease_id=early_blight.id)

    case.refresh_from_db()
    assert case.status == Case.Status.DIAGNOSED
    assert case.final_diagnosis.confidence == "low"


def test_similar_cases_ignore_other_wards_and_old_cases(case, near, far, late_blight):
    add_ai(case, "late blight")
    confirmed_nearby(late_blight, 3, far, ward="Mitheru")
    FinalDiagnosis.objects.filter(ward="Mitheru").update(latitude="-1.000000", longitude="38.000000")
    confirmed_nearby(late_blight, 1, far)
    FinalDiagnosis.objects.filter(ward="Chuka").update(created_at=timezone.now() - timedelta(days=60))

    assert review.similar_cases(case)["total"] == 0


def test_ai_disagreement_goes_to_second_opinion_with_another_agrovet(
    case, near, far, late_blight, early_blight, django_capture_on_commit_callbacks
):
    add_ai(case, "late blight")
    pending = first_review(case, near)

    with django_capture_on_commit_callbacks(execute=True):
        review.decide(agrovet_user=near.user, review=pending, disease_id=early_blight.id)

    case.refresh_from_db()
    assert case.status == Case.Status.SECOND_OPINION
    second = AgrovetReview.objects.get(case=case, status="pending")
    assert (second.agrovet, second.round) == (far, 2)


def test_history_majority_disagreement_goes_to_second_opinion(case, near, far, late_blight, early_blight):
    confirmed_nearby(late_blight, 4, far)
    confirmed_nearby(early_blight, 1, far)
    pending = first_review(case, near)

    review.decide(agrovet_user=near.user, review=pending, disease_id=early_blight.id)

    case.refresh_from_db()
    assert case.status == Case.Status.SECOND_OPINION


def test_ai_saying_healthy_disagrees_with_a_disease(case, near, late_blight):
    add_ai(case, "healthy", healthy=True)
    review.decide(agrovet_user=near.user, review=first_review(case, near), disease_id=late_blight.id)
    case.refresh_from_db()
    assert case.status == Case.Status.SECOND_OPINION


def test_unsure_first_agrovet_goes_to_second_opinion(case, near, far):
    review.decide(agrovet_user=near.user, review=first_review(case, near), unsure=True)
    case.refresh_from_db()
    assert case.status == Case.Status.SECOND_OPINION


# --- 3.6 Second opinion ---------------------------------------------------------------


def _to_second_opinion(case, first_agrovet, second_agrovet, first_disease):
    add_ai(case, "late blight")
    review.decide(
        agrovet_user=first_agrovet.user, review=first_review(case, first_agrovet), disease_id=first_disease.id
    )
    case.refresh_from_db()
    assert case.status == Case.Status.SECOND_OPINION
    return AgrovetReview.objects.create(case=case, agrovet=second_agrovet, round=2)


def test_second_opinion_agreeing_with_first_agrovet_diagnoses_and_rewards_trust(
    case, near, far, late_blight, early_blight
):
    second = _to_second_opinion(case, near, far, early_blight)

    review.decide(agrovet_user=far.user, review=second, disease_id=early_blight.id)

    case.refresh_from_db()
    assert case.status == Case.Status.DIAGNOSED
    assert (case.final_diagnosis.disease, case.final_diagnosis.confirmed_by) == (early_blight, far)
    near.refresh_from_db()
    assert near.trust_score == Decimal("1.00")
    assert TrustEvent.objects.get(user=near.user).reason == "diagnosis_confirmed"


def test_second_opinion_agreeing_with_ai_overrules_first_agrovet(case, near, far, late_blight, early_blight):
    second = _to_second_opinion(case, near, far, early_blight)

    review.decide(agrovet_user=far.user, review=second, disease_id=late_blight.id)

    case.refresh_from_db()
    assert case.final_diagnosis.disease == late_blight
    near.refresh_from_db()
    assert near.trust_score == Decimal("-2.00")


def test_no_agreement_after_second_opinion_is_unknown(case, near, far, late_blight, early_blight):
    septoria = Disease.objects.create(name="Septoria leaf spot")
    second = _to_second_opinion(case, near, far, early_blight)

    review.decide(agrovet_user=far.user, review=second, disease_id=septoria.id)

    case.refresh_from_db()
    assert case.status == Case.Status.UNKNOWN
    assert not FinalDiagnosis.objects.filter(case=case).exists()


def test_unsure_second_opinion_is_unknown_without_trust_change(case, near, far, late_blight, early_blight):
    second = _to_second_opinion(case, near, far, early_blight)
    review.decide(agrovet_user=far.user, review=second, unsure=True)
    case.refresh_from_db()
    assert case.status == Case.Status.UNKNOWN
    assert not TrustEvent.objects.exists()


# --- Decision rules ------------------------------------------------------------------------


def test_only_the_assigned_verified_agrovet_can_decide(case, near, far, late_blight):
    pending = first_review(case, near)
    with pytest.raises(review.DiagnoseNotFound):
        review.decide(agrovet_user=far.user, review=pending, disease_id=late_blight.id)
    Agrovet.objects.filter(pk=near.pk).update(status=Agrovet.Status.SUSPENDED)
    near.user.refresh_from_db()
    with pytest.raises(review.DiagnosePermissionDenied):
        review.decide(
            agrovet_user=User.objects.get(pk=near.user.pk), review=pending, disease_id=late_blight.id
        )


def test_review_cannot_be_decided_twice(case, near, late_blight):
    pending = first_review(case, near)
    review.decide(agrovet_user=near.user, review=pending, disease_id=late_blight.id)
    with pytest.raises(review.DiagnoseConflict):
        review.decide(agrovet_user=near.user, review=pending, disease_id=late_blight.id)


# --- 3.3 Peer input ----------------------------------------------------------------------------


@pytest.fixture
def peer(db):
    peer = make_farmer("+254711111111")
    make_case(peer, status=Case.Status.VERIFIED)  # one verified purchase
    FarmerProfile.objects.filter(user=peer).update(trust_score=5)
    return peer


def test_trusted_peer_in_ward_can_comment_with_weight(case, peer, late_blight):
    assert list(review.cases_open_for_peer(peer)) == [case]

    comment = review.add_peer_comment(
        user=peer, case=case, disease_id=late_blight.id, comment="Seen it on my farm"
    )

    assert comment.weight == Decimal("1.5")
    summary = review.peer_summary(case)
    assert summary["by_disease"][0] == {
        "disease_id": str(late_blight.id),
        "name": "Late blight",
        "weight": 1.5,
        "count": 1,
    }
    assert list(review.cases_open_for_peer(peer)) == []  # already commented
    with pytest.raises(review.DiagnoseConflict):
        review.add_peer_comment(user=peer, case=case, comment="again")


def test_peer_without_verified_purchase_or_from_other_ward_cannot_comment(case):
    newcomer = make_farmer("+254722222222")
    with pytest.raises(review.DiagnosePermissionDenied):
        review.add_peer_comment(user=newcomer, case=case, comment="Looks like blight")

    outsider = make_farmer("+254733333333", ward="Mitheru")
    make_case(outsider, status=Case.Status.VERIFIED, ward="Mitheru")
    with pytest.raises(review.DiagnoseNotFound):
        review.add_peer_comment(user=outsider, case=case, comment="Looks like blight")


@override_settings(DIAGNOSE={**review.settings.DIAGNOSE, "PEER_MIN_VERIFIED_PURCHASES": 0})
def test_case_owner_cannot_comment_on_own_case(farmer, case):
    with pytest.raises(review.DiagnoseNotFound):
        review.add_peer_comment(user=farmer, case=case, comment="mine")


# --- API ----------------------------------------------------------------------------------------


def test_agrovet_review_api_flow(farmer, case, near, far, late_blight, peer):
    add_ai(case, "late blight")
    review.add_peer_comment(user=peer, case=case, disease_id=late_blight.id)
    pending = first_review(case, near)
    api = client_for(near.user)

    listed = api.get(reverse("v1:agrovet-review-list"))
    assert listed.status_code == 200
    assert [r["id"] for r in listed.data] == [str(pending.id)]

    detail = api.get(reverse("v1:agrovet-review-detail", kwargs={"pk": pending.id}))
    assert detail.status_code == 200
    assert detail.data["case"]["ward"] == "Chuka"
    assert "farmer" not in detail.data["case"]
    assert detail.data["ai_diagnosis"]["suggestions"][0]["name"] == "late blight"
    assert detail.data["evidence"]["peers"]["count"] == 1

    # The reviewing agrovet may read the AI result but not spend credits re-running it.
    ai_url = reverse("v1:case-ai-diagnosis", kwargs={"case_id": case.id})
    assert api.get(ai_url).status_code == 200
    assert api.post(ai_url).status_code == 403

    other = client_for(far.user)
    assert other.get(reverse("v1:agrovet-review-detail", kwargs={"pk": pending.id})).status_code == 404
    assert client_for(farmer).get(reverse("v1:agrovet-review-list")).status_code == 403

    decide_url = reverse("v1:agrovet-review-decide", kwargs={"pk": pending.id})
    assert api.post(decide_url, {}, format="json").status_code == 400
    decided = api.post(decide_url, {"disease_id": str(late_blight.id), "notes": "ok"}, format="json")
    assert decided.status_code == 200, decided.data
    assert decided.data["decision"] == "disease"

    status = client_for(farmer).get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id}))
    assert status.status_code == 200
    assert status.data["status"] == "DIAGNOSED"
    assert status.data["disease"]["name"] == "Late blight"
    assert status.data["confirmed_by"] == "near"
    assert "Late blight" in status.data["message"]


def test_farmer_lists_and_chooses_agrovet_via_api(farmer, near, far):
    case = make_case(farmer, status=Case.Status.REPORTED)
    api = client_for(farmer)
    url = reverse("v1:case-agrovets", kwargs={"case_id": case.id})

    listed = api.get(url)
    assert [a["name"] for a in listed.data] == ["near", "far"]
    assert listed.data[0]["distance_km"] < listed.data[1]["distance_km"]

    chosen = api.post(url, {"agrovet_id": str(far.id)}, format="json")
    assert chosen.status_code == 201
    status = api.get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id}))
    assert status.data["reviewer"]["name"] == "far"


def test_unknown_case_tells_farmer_to_visit_plant_clinic(farmer):
    case = make_case(farmer, status=Case.Status.UNKNOWN)
    status = client_for(farmer).get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id}))
    assert "kliniki ya mimea" in status.data["message"]  # default language is Swahili
    FarmerProfile.objects.filter(user=farmer).update(language="en")
    status = client_for(farmer).get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id}))
    assert "plant clinic" in status.data["message"]


def test_peer_api(case, peer, late_blight):
    api = client_for(peer)
    listed = api.get(reverse("v1:peer-cases"))
    assert listed.status_code == 200
    assert listed.data[0]["id"] == str(case.id)
    assert "farmer" not in listed.data[0]

    url = reverse("v1:case-peer-comments", kwargs={"case_id": case.id})
    created = api.post(url, {"disease_id": str(late_blight.id), "comment": "Same on mine"}, format="json")
    assert created.status_code == 201, created.data
    assert api.post(url, {"comment": "again"}, format="json").status_code == 409


def test_disease_list(farmer, late_blight, early_blight):
    Disease.objects.create(name="Retired", is_active=False)
    names = [d["name"] for d in client_for(farmer).get(reverse("v1:diseases")).data]
    assert names == ["Early blight", "Late blight"]
