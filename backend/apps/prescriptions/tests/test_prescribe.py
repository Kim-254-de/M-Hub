"""Prescribe processes 4.1-4.5 and conflict-of-interest monitoring."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmerProfile, User
from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.diagnosis.models import FinalDiagnosis
from apps.prescriptions import services
from apps.prescriptions.models import Prescription, TreatmentOutcome
from apps.products.models import Disease, Product, TreatmentRule
from apps.purchases.services import find_stores
from apps.rewards.models import TrustEvent

pytestmark = pytest.mark.django_db

LAT, LNG = "-0.333000", "37.650000"


def client_for(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def make_agrovet(username, status=Agrovet.Status.VERIFIED):
    user = User.objects.create_user(username=username, password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user,
        name=username,
        pcpb_licence_no=f"LIC-{username}",
        latitude=LAT,
        longitude="37.658000",
        status=status,
    )


def make_product(reg, name, ingredients, crops=("tomato",), phi=7, rate=None, unit="", pack=None, **extra):
    return Product.objects.create(
        pcpb_reg_no=reg,
        name=name,
        active_ingredients=list(ingredients),
        approved_crops=list(crops),
        phi_days=phi,
        rate_per_acre=rate,
        rate_unit=unit,
        pack_size=pack,
        **extra,
    )


def add_outcomes(product, disease, improved, total, *, ward="Chuka", status=Case.Status.VERIFIED):
    farmer = User.objects.create_user(
        username=f"o{TreatmentOutcome.objects.count()}-{product.pk}", password="x"
    )
    for i in range(total):
        case = Case.objects.create(farmer=farmer, status=status, ward=ward)
        TreatmentOutcome.objects.create(
            case=case, farmer=farmer, disease=disease, product=product, improved=i < improved, ward=ward
        )


@pytest.fixture
def farmer(db):
    user = User.objects.create_user(username="farmer", password="x", phone="+254700000001")
    FarmerProfile.objects.create(user=user, ward="Chuka", county="Tharaka Nithi", consent_at=timezone.now())
    return user


@pytest.fixture
def agrovet(db):
    return make_agrovet("chuka-agrovet")


@pytest.fixture
def late_blight(db):
    disease = Disease.objects.create(name="Late blight")
    TreatmentRule.objects.create(disease=disease, active_ingredient="Mancozeb")
    TreatmentRule.objects.create(disease=disease, active_ingredient="metalaxyl-M")
    return disease


@pytest.fixture
def ridomil(db):
    return make_product(
        "PCPB (CR) 0856",
        "Ridomil Gold MZ 68 WG",
        ["Metalaxyl-M", "mancozeb"],
        phi=7,
        rate=Decimal("250"),
        unit="g",
        pack=Decimal("250"),
        ppe_notes="Wear gloves, mask and boots.",
    )


@pytest.fixture
def dithane(db):
    return make_product("PCPB (CR) 1201", "Dithane M-45", ["mancozeb"], phi=3)


@pytest.fixture
def not_allowed(db):
    make_product("PCPB (CR) 0333", "Duduthrin", ["lambda-cyhalothrin"])  # wrong ingredient
    make_product("PCPB (CR) 0444", "Potato-only mancozeb", ["mancozeb"], crops=["potato"])
    make_product("PCPB (CR) 0555", "Cancelled mancozeb", ["mancozeb"], is_active=False)


@pytest.fixture
def case(farmer, agrovet, late_blight):
    farm = Farm.objects.create(farmer=farmer, latitude=LAT, longitude=LNG, size_acres="0.50")
    case = Case.objects.create(
        farmer=farmer, farm=farm, status=Case.Status.DIAGNOSED, ward="Chuka", latitude=LAT, longitude=LNG
    )
    FinalDiagnosis.objects.create(
        case=case, disease=late_blight, confidence="high", confirmed_by=agrovet, ward="Chuka"
    )
    return case


# --- 4.1 Rule filter -------------------------------------------------------------------


def test_only_registered_tomato_products_for_the_disease_are_allowed(
    late_blight, ridomil, dithane, not_allowed
):
    assert {p.name for p in services.allowed_products(late_blight)} == {
        "Ridomil Gold MZ 68 WG",
        "Dithane M-45",
    }


def test_disease_without_rules_allows_nothing(ridomil):
    assert services.allowed_products(Disease.objects.create(name="Bacterial wilt")) == []


# --- 4.2 Ranking ---------------------------------------------------------------------------


def test_without_local_data_ranks_by_label_guidance(case, late_blight, ridomil, dithane):
    options = services.rank_products(case, late_blight, [ridomil, dithane])
    assert [o["name"] for o in options] == ["Dithane M-45", "Ridomil Gold MZ 68 WG"]  # shorter PHI first
    assert all(o["evidence_text"] == "Not enough local data yet" for o in options)
    assert [o["rank"] for o in options] == [1, 2]


def test_local_evidence_ranks_first_and_needs_minimum_verified_reports(case, late_blight, ridomil, dithane):
    add_outcomes(ridomil, late_blight, improved=18, total=23)
    add_outcomes(dithane, late_blight, improved=4, total=4)  # below the minimum of 5
    add_outcomes(dithane, late_blight, improved=5, total=5, status=Case.Status.PURCHASED)  # unverified
    add_outcomes(dithane, late_blight, improved=5, total=5, ward="Faraway")  # not nearby (no GPS either)

    options = services.rank_products(case, late_blight, [ridomil, dithane])

    assert options[0]["name"] == "Ridomil Gold MZ 68 WG"
    assert options[0]["evidence_text"] == "18 of 23 verified farmers nearby saw the spread stop"
    assert options[1]["local_evidence"] is False


# --- 4.3 Dose -------------------------------------------------------------------------------


def test_dose_is_farm_size_times_label_rate_in_whole_packs(ridomil):
    dose = services.calculate_dose(ridomil, Decimal("0.50"))
    assert dose.quantity == "1 pack of 250 g (125 g needed)"
    assert services.calculate_dose(ridomil, Decimal("2.2")).quantity == "3 packs of 250 g (550 g needed)"


def test_dose_without_numeric_rate_says_follow_the_label(dithane):
    dithane.label_rate = "50 g per 20 L"
    dose = services.calculate_dose(dithane, Decimal("1"))
    assert dose.follow_label and dose.quantity == "Follow the label: 50 g per 20 L"


# --- 4.4 / 4.5 Approval ----------------------------------------------------------------------


def test_approval_issues_code_and_moves_case_to_prescribed(
    case, agrovet, late_blight, ridomil, dithane, not_allowed
):
    prescription = services.approve(agrovet_user=agrovet.user, case=case, product_id=ridomil.id)

    assert prescription.code.startswith("AGR-") and len(prescription.code) == 10
    assert prescription.approved_product == ridomil
    assert prescription.quantity == "1 pack of 250 g (125 g needed)"
    assert prescription.disease == late_blight
    assert set(prescription.allowed_products.all()) == {ridomil, dithane}
    assert [o["name"] for o in prescription.ranking] == ["Dithane M-45", "Ridomil Gold MZ 68 WG"]
    assert prescription.expires_at > timezone.now()
    case.refresh_from_db()
    assert case.status == Case.Status.PRESCRIBED

    with pytest.raises(services.PrescribeConflict):
        services.approve(agrovet_user=agrovet.user, case=case, product_id=ridomil.id)


def test_agrovet_cannot_prescribe_outside_the_allowed_list(case, agrovet, ridomil, not_allowed):
    duduthrin = Product.objects.get(name="Duduthrin")
    with pytest.raises(services.PrescribeError) as exc:
        services.approve(agrovet_user=agrovet.user, case=case, product_id=duduthrin.id)
    assert exc.value.code == "product_not_allowed"


def test_only_the_confirming_verified_agrovet_prescribes(case, agrovet, ridomil):
    other = make_agrovet("other")
    with pytest.raises(services.PrescribeNotFound):
        services.approve(agrovet_user=other.user, case=case, product_id=ridomil.id)
    Agrovet.objects.filter(pk=agrovet.pk).update(status=Agrovet.Status.SUSPENDED)
    with pytest.raises(services.PrescribePermissionDenied):
        services.approve(agrovet_user=User.objects.get(pk=agrovet.user.pk), case=case, product_id=ridomil.id)


def test_no_allowed_product_is_reported(case, agrovet, not_allowed):
    with pytest.raises(services.PrescribeConflict) as exc:
        services.approve(agrovet_user=agrovet.user, case=case, product_id=Product.objects.first().id)
    assert exc.value.code == "no_allowed_products"


def test_prescription_flows_into_buy_genuine_product(case, agrovet, ridomil, dithane):
    StoreItem.objects.create(agrovet=agrovet, product=dithane, price_kes=300)  # the swap option, in stock
    prescription = services.approve(agrovet_user=agrovet.user, case=case, product_id=ridomil.id)

    offers = find_stores(prescription)

    assert [o.store_item.product for o in offers] == [dithane]


# --- API ---------------------------------------------------------------------------------------


def test_prescribe_api_flow(farmer, case, agrovet, ridomil, dithane):
    api = client_for(agrovet.user)

    draft = api.get(reverse("v1:prescription-draft", kwargs={"case_id": case.id}))
    assert draft.status_code == 200, draft.data
    assert draft.data["local_data"] is False
    assert [o["name"] for o in draft.data["options"]] == ["Dithane M-45", "Ridomil Gold MZ 68 WG"]
    assert draft.data["options"][1]["quantity"] == "1 pack of 250 g (125 g needed)"

    approved = api.post(
        reverse("v1:prescription-approve", kwargs={"case_id": case.id}),
        {"product_id": str(ridomil.id)},
        format="json",
    )
    assert approved.status_code == 201, approved.data
    assert approved.data["qr_payload"] == approved.data["code"]

    card = client_for(farmer).get(reverse("v1:case-prescription", kwargs={"case_id": case.id}))
    assert card.status_code == 200
    assert card.data["disease"] == "Late blight"
    assert card.data["approved_product"]["pcpb_reg_no"] == "PCPB (CR) 0856"
    assert {o["name"] for o in card.data["options"]} == {"Dithane M-45", "Ridomil Gold MZ 68 WG"}
    assert card.data["safety_notes"] == "Wear gloves, mask and boots."
    assert card.data["phi_days"] == 7
    assert card.data["approved_by"] == "chuka-agrovet"
    # Profiles default to Kiswahili: dose and safety are templated in the farmer's language.
    instructions = card.data["instructions"]
    assert instructions["language"] == "sw"
    assert instructions["dose"] == "Nunua 1 x 250 g. Changanya 125 g kwa kunyunyizia shamba lako mara moja."
    assert instructions["harvest"] == "Usivune kwa siku 7 baada ya kunyunyizia."
    assert instructions["label_notes"] == "Wear gloves, mask and boots."


def test_prescribe_api_rejects_others(farmer, case, ridomil):
    other = make_agrovet("other")
    assert (
        client_for(other.user).get(reverse("v1:prescription-draft", kwargs={"case_id": case.id})).status_code
        == 404
    )
    assert (
        client_for(farmer).get(reverse("v1:prescription-draft", kwargs={"case_id": case.id})).status_code
        == 403
    )
    stranger = User.objects.create_user(username="stranger", password="x")
    assert (
        client_for(stranger).get(reverse("v1:case-prescription", kwargs={"case_id": case.id})).status_code
        == 403
    )


# --- Conflict of interest --------------------------------------------------------------------------


def test_agrovet_favouring_price_over_evidence_loses_trust_once_per_quarter(agrovet):
    ranking = [
        {"rank": 1, "product_id": "a", "name": "A", "local_evidence": True, "avg_price_kes": 400},
        {"rank": 2, "product_id": "b", "name": "B", "local_evidence": False, "avg_price_kes": 900},
    ]
    product = make_product("PCPB (CR) 0900", "B", ["x"])
    farmer = User.objects.create_user(username="f", password="x")
    for _ in range(5):
        case = Case.objects.create(farmer=farmer, status=Case.Status.PRESCRIBED)
        ranking_b = [dict(r, product_id=str(product.id)) if r["rank"] == 2 else r for r in ranking]
        Prescription.objects.create(
            case=case,
            approved_product=product,
            approved_by=agrovet,
            expires_at=timezone.now(),
            ranking=ranking_b,
        )

    assert services.review_prescribing_patterns() == 1
    assert services.review_prescribing_patterns() == 0
    agrovet.refresh_from_db()
    assert agrovet.trust_score == Decimal("-5.00")
    assert TrustEvent.objects.get().reason == "prescribing_pattern"


def test_choosing_the_better_or_cheaper_option_is_not_flagged():
    ranking = [
        {"rank": 1, "product_id": "a", "local_evidence": True, "avg_price_kes": 400},
        {"rank": 2, "product_id": "b", "local_evidence": False, "avg_price_kes": 300},
    ]
    assert not services.favours_price_over_evidence(ranking, "a")
    assert not services.favours_price_over_evidence(
        ranking, "b"
    )  # cheaper: e.g. out of stock or affordability
