"""One case through every module over the API: Detect -> Diagnose -> Prescribe -> Buy -> Verified."""

import copy
from decimal import Decimal

import pytest
import responses
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmerProfile, User
from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.cases.tests.conftest import VALID_ANSWERS, image_bytes, sharp_pixels
from apps.diagnosis.tests.conftest import KINDWISE_RESPONSE, KINDWISE_URL
from apps.products.models import Disease, Product, TreatmentRule
from apps.purchases.tests.conftest import OCR_URL, ocr_response

pytestmark = pytest.mark.django_db


def client_for(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def world(db):
    farmer = User.objects.create_user(username="wanjiru", password="x", phone="+254712345678")
    FarmerProfile.objects.create(user=farmer, county="Tharaka Nithi", ward="Chuka", consent_at=timezone.now())
    farm = Farm.objects.create(farmer=farmer, latitude="-0.333000", longitude="37.650000", size_acres="0.50")

    agrovet_user = User.objects.create_user(username="chuka-agrovet", password="x", role=User.Role.AGROVET)
    agrovet = Agrovet.objects.create(
        user=agrovet_user,
        name="Chuka Agrovet",
        pcpb_licence_no="LIC-1",
        has_qualified_staff=True,
        latitude="-0.330000",
        longitude="37.658000",
        status=Agrovet.Status.VERIFIED,
    )

    late_blight = Disease.objects.create(name="Late blight", scientific_name="Phytophthora infestans")
    TreatmentRule.objects.create(disease=late_blight, active_ingredient="mancozeb")
    ridomil = Product.objects.create(
        pcpb_reg_no="PCPB (CR) 0856",
        name="Ridomil Gold MZ 68 WG",
        active_ingredients=["metalaxyl-M", "mancozeb"],
        approved_crops=["tomato"],
        phi_days=7,
        rate_per_acre=Decimal("250"),
        rate_unit="g",
        pack_size=Decimal("250"),
    )
    store_item = StoreItem.objects.create(agrovet=agrovet, product=ridomil, price_kes=650)
    return {
        "farmer": farmer,
        "farm": farm,
        "agrovet": agrovet,
        "disease": late_blight,
        "product": ridomil,
        "item": store_item,
    }


@responses.activate
def test_case_goes_from_report_to_verified_purchase(world, django_capture_on_commit_callbacks):
    farmer_api = client_for(world["farmer"])
    agrovet_api = client_for(world["agrovet"].user)

    # Module 1: Detect
    created = farmer_api.post(reverse("v1:case-list"), {"farm": str(world["farm"].id)}, format="json")
    assert created.status_code == 201
    case_id = created.data["id"]
    for photo_type in ("leaf", "plant", "stem_fruit"):
        photo = SimpleUploadedFile(
            f"{photo_type}.jpg", image_bytes(sharp_pixels()), content_type="image/jpeg"
        )
        uploaded = farmer_api.post(
            reverse("v1:case-photos", kwargs={"pk": case_id}),
            {"type": photo_type, "image": photo},
            format="multipart",
        )
        assert uploaded.status_code == 201, uploaded.data
    assert (
        farmer_api.put(
            reverse("v1:case-answers", kwargs={"pk": case_id}), VALID_ANSWERS, format="json"
        ).status_code
        == 200
    )

    # Module 2: Diagnose. Submitting runs the AI (eager Celery) and assigns the nearest agrovet.
    responses.post(KINDWISE_URL, json=copy.deepcopy(KINDWISE_RESPONSE), status=201)
    with django_capture_on_commit_callbacks(execute=True):
        submitted = farmer_api.post(reverse("v1:case-submit", kwargs={"pk": case_id}))
    assert submitted.status_code == 202
    assert Case.objects.get(pk=case_id).status == Case.Status.DIAGNOSING

    reviews = agrovet_api.get(reverse("v1:agrovet-review-list")).data
    assert len(reviews) == 1 and reviews[0]["case_id"] == case_id
    decided = agrovet_api.post(
        reverse("v1:agrovet-review-decide", kwargs={"pk": reviews[0]["id"]}),
        {"disease_id": str(world["disease"].id)},
        format="json",
    )
    assert decided.status_code == 200, decided.data
    diagnosis = farmer_api.get(reverse("v1:case-diagnosis", kwargs={"case_id": case_id})).data
    assert (diagnosis["status"], diagnosis["disease"]["name"], diagnosis["confidence"]) == (
        "DIAGNOSED",
        "Late blight",
        "medium",
    )

    # Module 3: Prescribe
    draft = agrovet_api.get(reverse("v1:prescription-draft", kwargs={"case_id": case_id})).data
    approved = agrovet_api.post(
        reverse("v1:prescription-approve", kwargs={"case_id": case_id}),
        {"product_id": draft["options"][0]["product_id"]},
        format="json",
    )
    assert approved.status_code == 201, approved.data
    card = farmer_api.get(reverse("v1:case-prescription", kwargs={"case_id": case_id})).data
    code = card["code"]
    assert card["quantity"] == "1 pack of 250 g (125 g needed)"

    # Module 4: Buy Genuine Product
    stores = farmer_api.get(reverse("v1:prescription-stores", kwargs={"code": code})).data
    assert [s["store_item_id"] for s in stores] == [str(world["item"].id)]
    order = farmer_api.post(
        reverse("v1:order-list"),
        {
            "prescription_code": code,
            "store_item_id": stores[0]["store_item_id"],
            "quantity": 1,
            "payment_method": "pay_at_shop",
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    sale = agrovet_api.post(
        reverse("v1:sale-match"),
        {"prescription_code": code, "product_id": str(world["product"].id)},
        format="json",
    )
    assert sale.status_code == 201, sale.data
    assert Case.objects.get(pk=case_id).status == Case.Status.PURCHASED

    responses.post(OCR_URL, json=ocr_response("RIDOMIL GOLD\nPCPB (CR) 0856\nSyngenta"))
    label = SimpleUploadedFile("label.jpg", image_bytes(sharp_pixels()), content_type="image/jpeg")
    checked = farmer_api.post(
        reverse("v1:order-label-check", kwargs={"pk": order.data["id"]}), {"photo": label}, format="multipart"
    )
    assert checked.status_code == 201, checked.data
    assert checked.data["result"] == "verified"

    assert Case.objects.get(pk=case_id).status == Case.Status.VERIFIED
    assert farmer_api.get(reverse("v1:my-rewards")).data["balance"] == 10
    assert FarmerProfile.objects.get(user=world["farmer"]).trust_score == Decimal("1.00")
