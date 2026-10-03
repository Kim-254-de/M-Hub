import io
from datetime import timedelta

import pytest
import responses
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.prescriptions.models import Prescription
from apps.products.models import Product

MPESA = "https://mpesa.test"
OAUTH_URL = f"{MPESA}/oauth/v1/generate"
STK_URL = f"{MPESA}/mpesa/stkpush/v1/processrequest"
QUERY_URL = f"{MPESA}/mpesa/stkpushquery/v1/query"
OCR_URL = "https://ocr.test/parse/image"
CALLBACK_PATH = "/api/v1/payments/mpesa/callback/test-callback-token/"

# Chuka, Tharaka Nithi
FARM_LAT, FARM_LNG = "-0.333000", "37.650000"


def image_bytes(size=(800, 600)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (220, 220, 220)).save(buffer, format="JPEG")
    return buffer.getvalue()


def ocr_response(text):
    return {
        "ParsedResults": [
            {"FileParseExitCode": 1, "ParsedText": text, "ErrorMessage": "", "ErrorDetails": ""}
        ],
        "OCRExitCode": 1,
        "IsErroredOnProcessing": False,
        "ProcessingTimeInMilliseconds": "812",
    }


def stk_callback(checkout_id, *, result_code=0, amount=1300, receipt="SJK7RT61SV", phone=254712345678):
    callback = {
        "MerchantRequestID": "29115-34620561-1",
        "CheckoutRequestID": checkout_id,
        "ResultCode": result_code,
        "ResultDesc": "The service request is processed successfully."
        if result_code == 0
        else "Request cancelled by user",
    }
    if result_code == 0:
        callback["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": amount},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20261003102115},
                {"Name": "PhoneNumber", "Value": phone},
            ]
        }
    return {"Body": {"stkCallback": callback}}


def mock_stk_push(checkout_id="ws_CO_03102026102115123456"):
    responses.get(OAUTH_URL, json={"access_token": "token-abc", "expires_in": "3599"})
    responses.post(
        STK_URL,
        json={
            "MerchantRequestID": "29115-34620561-1",
            "CheckoutRequestID": checkout_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        },
    )
    return checkout_id


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def farmer(db):
    return User.objects.create_user(username="farmer", password="x", phone="0712345678")


@pytest.fixture
def other_farmer(db):
    return User.objects.create_user(username="farmer2", password="x", phone="0722000000")


def make_agrovet(username, *, name, lat, lng, status=Agrovet.Status.VERIFIED):
    user = User.objects.create_user(username=username, password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user,
        name=name,
        pcpb_licence_no=f"LIC-{username}",
        has_qualified_staff=True,
        phone="0700111222",
        latitude=lat,
        longitude=lng,
        status=status,
    )


@pytest.fixture
def agrovet(db):
    # ~1 km from the farm
    return make_agrovet("agro1", name="Chuka Agrovet", lat="-0.330000", lng="37.658000")


@pytest.fixture
def far_agrovet(db):
    # ~10 km away
    return make_agrovet("agro2", name="Chogoria Farm Inputs", lat="-0.240000", lng="37.640000")


@pytest.fixture
def product(db):
    return Product.objects.create(
        pcpb_reg_no="PCPB (CR) 0856",
        name="Ridomil Gold MZ 68 WG",
        active_ingredients=["metalaxyl-M", "mancozeb"],
        approved_crops=["tomato"],
        phi_days=7,
    )


@pytest.fixture
def alt_product(db):
    return Product.objects.create(pcpb_reg_no="PCPB (CR) 1201", name="Mancozeb 80 WP", phi_days=7)


@pytest.fixture
def unprescribed_product(db):
    return Product.objects.create(pcpb_reg_no="PCPB (CR) 0333", name="Duduthrin 1.75 EC", phi_days=3)


@pytest.fixture
def case(farmer):
    return Case.objects.create(
        farmer=farmer, status=Case.Status.PRESCRIBED, latitude=FARM_LAT, longitude=FARM_LNG
    )


@pytest.fixture
def prescription(case, agrovet, product, alt_product):
    p = Prescription.objects.create(
        case=case,
        approved_product=product,
        quantity="2 x 250 g",
        approved_by=agrovet,
        expires_at=timezone.now() + timedelta(days=7),
    )
    p.allowed_products.set([product, alt_product])
    return p


@pytest.fixture
def store_item(agrovet, product):
    return StoreItem.objects.create(agrovet=agrovet, product=product, price_kes=650)


@pytest.fixture
def mpesa_order(farmer, prescription, store_item):
    from apps.purchases.services import create_order

    return create_order(
        farmer=farmer,
        prescription=prescription,
        store_item_id=store_item.id,
        quantity=2,
        payment_method="mpesa",
    )
