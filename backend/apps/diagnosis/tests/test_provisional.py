"""Farmer-facing provisional AI result and safe first steps while an agrovet confirms."""

import json

import pytest
from django.urls import reverse

from apps.accounts.models import FarmerProfile
from apps.cases.models import Case
from apps.diagnosis.messages import GENERAL_SAFE_ACTIONS
from apps.diagnosis.models import AIDiagnosis, FinalDiagnosis
from apps.products.models import Disease, Product

from .test_review import add_ai, client_for, make_agrovet, make_case, make_farmer

pytestmark = pytest.mark.django_db

LATE_BLIGHT_STEPS = ["Remove and bury every leaf with dark, water-soaked patches today."]


@pytest.fixture
def farmer(db):
    farmer = make_farmer("+254700000001")
    FarmerProfile.objects.filter(user=farmer).update(language="en")
    return farmer


@pytest.fixture
def late_blight(db):
    return Disease.objects.create(
        name="Late blight",
        scientific_name="Phytophthora infestans",
        local_names={"sw": "Baa chelewa"},
        safe_actions={"en": LATE_BLIGHT_STEPS},
    )


def diagnosis(farmer, case):
    response = client_for(farmer).get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id}))
    assert response.status_code == 200
    return response.data


def test_likely_disease_is_shown_with_its_reviewed_steps(farmer, late_blight):
    case = make_case(farmer)
    add_ai(case, "late blight", probability="0.9200")

    data = diagnosis(farmer, case)

    assert data["provisional"]["kind"] == "likely"
    assert data["provisional"]["disease"]["name"] == "Late blight"
    assert data["provisional"]["message"].startswith(
        "Likely Late blight (92%). This is a computer suggestion"
    )
    assert data["safe_actions"] == LATE_BLIGHT_STEPS
    assert data["disease"] is None and data["ai_corrected"] is None


def test_swahili_farmer_sees_local_name_and_general_steps_in_swahili(farmer, late_blight):
    FarmerProfile.objects.filter(user=farmer).update(language="sw")
    case = make_case(farmer)
    add_ai(case, "late blight")

    data = diagnosis(farmer, case)

    assert data["provisional"]["message"].startswith("Huenda ni Baa chelewa (92%)")
    # The reviewed late blight steps exist only in English, so the general Swahili steps are shown.
    assert data["safe_actions"] == GENERAL_SAFE_ACTIONS["sw"]


def test_disease_outside_the_catalogue_uses_the_ai_name_and_general_steps(farmer, late_blight):
    case = make_case(farmer)
    add_ai(case, "septoria leaf spot", probability="0.8100")

    data = diagnosis(farmer, case)

    assert data["provisional"]["kind"] == "likely"
    assert data["provisional"]["name"] == "septoria leaf spot"
    assert data["provisional"]["disease"] is None
    assert data["safe_actions"] == GENERAL_SAFE_ACTIONS["en"]


def test_low_probability_says_unsure_without_naming_a_disease(farmer, late_blight):
    case = make_case(farmer)
    add_ai(case, "late blight", probability="0.3000")

    provisional = diagnosis(farmer, case)["provisional"]

    assert provisional["kind"] == "unsure"
    assert provisional["name"] is None and provisional["probability"] is None
    assert "could not tell" in provisional["message"]


def test_healthy_suggestion(farmer):
    case = make_case(farmer)
    add_ai(case, "healthy", healthy=True)
    assert diagnosis(farmer, case)["provisional"]["kind"] == "healthy"


def test_nothing_provisional_while_ai_runs_or_photos_need_retaking(farmer):
    case = make_case(farmer, status=Case.Status.REPORTED)
    AIDiagnosis.objects.create(case=case, provider="kindwise")  # still pending

    data = diagnosis(farmer, case)
    assert data["provisional"] is None
    assert data["safe_actions"] == GENERAL_SAFE_ACTIONS["en"]

    AIDiagnosis.objects.filter(case=case).update(status=AIDiagnosis.Status.COMPLETED, is_plant=False)
    assert diagnosis(farmer, case)["provisional"] is None


def test_ai_is_not_repeated_during_a_second_opinion(farmer, late_blight):
    case = make_case(farmer, status=Case.Status.SECOND_OPINION)
    add_ai(case, "late blight")
    assert diagnosis(farmer, case)["provisional"] is None


def test_confirmation_replaces_the_provisional_result(farmer, late_blight):
    case = make_case(farmer, status=Case.Status.DIAGNOSED)
    add_ai(case, "late blight")
    FinalDiagnosis.objects.create(
        case=case, disease=late_blight, confidence="medium", confirmed_by=make_agrovet("a", "-0.33", "37.65")
    )

    data = diagnosis(farmer, case)

    assert data["provisional"] is None
    assert data["disease"]["name"] == "Late blight"
    assert data["ai_corrected"] is False and data["ai_corrected_message"] is None
    assert data["safe_actions"] == LATE_BLIGHT_STEPS


def test_farmer_is_told_when_the_agrovet_corrected_the_ai(farmer, late_blight):
    early_blight = Disease.objects.create(name="Early blight")
    case = make_case(farmer, status=Case.Status.PRESCRIBED)
    add_ai(case, "late blight")
    FinalDiagnosis.objects.create(
        case=case, disease=early_blight, confidence="medium", confirmed_by=make_agrovet("a", "-0.33", "37.65")
    )

    data = diagnosis(farmer, case)

    assert data["ai_corrected"] is True
    assert data["ai_corrected_message"].startswith("The agrovet's diagnosis is different")
    assert "Early blight" in data["message"]


def test_provisional_result_never_names_a_product(farmer, late_blight):
    Product.objects.create(pcpb_reg_no="PCPB (CR) 0856", name="Ridomil Gold MZ 68 WG")
    case = make_case(farmer)
    suggestion = add_ai(case, "late blight").suggestions.get()
    suggestion.details = {"treatment": {"chemical treatment": ["Apply Ridomil Gold every 7 days."]}}
    suggestion.save()

    data = diagnosis(farmer, case)

    assert "ridomil" not in json.dumps(data, default=str).lower()
