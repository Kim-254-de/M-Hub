from datetime import timedelta

import pytest
import responses
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.purchases import services
from apps.purchases.models import Order, Payment, StoreFlag, Verification
from apps.rewards.services import balance

from .conftest import (
    CALLBACK_PATH,
    OAUTH_URL,
    OCR_URL,
    QUERY_URL,
    STK_URL,
    client_for,
    image_bytes,
    make_agrovet,
    mock_stk_push,
    ocr_response,
    stk_callback,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def label_photo():
    return SimpleUploadedFile("label.jpg", image_bytes(), content_type="image/jpeg")


def collected_order(order, agrovet):
    Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID, paid_at=timezone.now())
    services.match_sale(agrovet_user=agrovet.user, code=order.prescription.code, product_id=order.product_id)
    order.refresh_from_db()
    return order


# --- 5.1 Find verified stores ----------------------------------------------------


def test_store_list_shows_only_verified_in_stock_prescribed_nearest_first(
    farmer, prescription, store_item, far_agrovet, alt_product, unprescribed_product
):
    StoreItem.objects.create(agrovet=far_agrovet, product=alt_product, price_kes=400)
    StoreItem.objects.create(
        agrovet=far_agrovet, product=unprescribed_product, price_kes=100
    )  # not prescribed
    pending = make_agrovet(
        "agro3", name="Unverified", lat="-0.331", lng="37.651", status=Agrovet.Status.PENDING
    )
    StoreItem.objects.create(agrovet=pending, product=store_item.product, price_kes=10)
    out_of_stock = make_agrovet("agro4", name="Empty Shelves", lat="-0.332", lng="37.652")
    StoreItem.objects.create(agrovet=out_of_stock, product=store_item.product, price_kes=10, in_stock=False)

    response = client_for(farmer).get(f"/api/v1/prescriptions/{prescription.code.lower()}/stores/")

    assert response.status_code == 200
    names = [o["agrovet_name"] for o in response.json()]
    assert names == ["Chuka Agrovet", "Chogoria Farm Inputs"]
    first = response.json()[0]
    assert first["price_kes"] == 650
    assert 0 < first["distance_km"] < 2
    assert first["product"]["pcpb_reg_no"] == "PCPB (CR) 0856"


def test_store_list_respects_radius(farmer, prescription, store_item, far_agrovet, alt_product):
    StoreItem.objects.create(agrovet=far_agrovet, product=alt_product, price_kes=400)
    response = client_for(farmer).get(f"/api/v1/prescriptions/{prescription.code}/stores/?radius_km=5")
    assert [o["agrovet_name"] for o in response.json()] == ["Chuka Agrovet"]


def test_store_list_hidden_from_other_farmers(other_farmer, prescription, store_item):
    response = client_for(other_farmer).get(f"/api/v1/prescriptions/{prescription.code}/stores/")
    assert response.status_code == 404


def test_expired_prescription_cannot_be_shopped(farmer, prescription, store_item):
    prescription.expires_at = timezone.now() - timedelta(minutes=1)
    prescription.save()
    response = client_for(farmer).get(f"/api/v1/prescriptions/{prescription.code}/stores/")
    assert response.status_code == 400
    assert response.json()["code"] == "prescription_expired"


# --- 5.2 Order and pay -----------------------------------------------------------


def order_body(prescription, store_item, **overrides):
    return {
        "prescription_code": prescription.code,
        "store_item_id": str(store_item.id),
        "quantity": 2,
        "payment_method": "mpesa",
        **overrides,
    }


def test_create_mpesa_order_snapshots_price(farmer, prescription, store_item):
    response = client_for(farmer).post("/api/v1/orders/", order_body(prescription, store_item), format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "awaiting_payment"
    assert body["unit_price_kes"] == 650 and body["total_kes"] == 1300

    store_item.price_kes = 999
    store_item.save()
    assert Order.objects.get(pk=body["id"]).total_kes == 1300


def test_pay_at_shop_order_is_reserved(farmer, prescription, store_item):
    response = client_for(farmer).post(
        "/api/v1/orders/", order_body(prescription, store_item, payment_method="pay_at_shop"), format="json"
    )
    assert response.json()["status"] == "reserved"


def test_one_open_order_per_prescription(farmer, prescription, store_item):
    client = client_for(farmer)
    client.post("/api/v1/orders/", order_body(prescription, store_item), format="json")
    response = client.post("/api/v1/orders/", order_body(prescription, store_item), format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "order_exists"


def test_cannot_order_unprescribed_product(farmer, prescription, agrovet, unprescribed_product):
    item = StoreItem.objects.create(agrovet=agrovet, product=unprescribed_product, price_kes=100)
    response = client_for(farmer).post("/api/v1/orders/", order_body(prescription, item), format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "product_not_prescribed"


@responses.activate
def test_full_mpesa_payment_flow(farmer, mpesa_order):
    checkout = mock_stk_push()
    client = client_for(farmer)

    response = client.post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")

    assert response.status_code == 202
    payment = Payment.objects.get(pk=response.json()["id"])
    assert payment.status == Payment.Status.PENDING
    assert payment.phone == "254712345678"  # account phone, normalised
    assert payment.checkout_request_id == checkout
    stk_body = responses.calls[1].request.body
    assert b"https://api.agrisense.test" + CALLBACK_PATH.encode() in stk_body

    callback = APIClient().post(CALLBACK_PATH, stk_callback(checkout), format="json")
    assert callback.status_code == 200 and callback.json()["ResultCode"] == 0

    payment.refresh_from_db()
    mpesa_order.refresh_from_db()
    assert payment.status == Payment.Status.SUCCESS and payment.mpesa_receipt == "SJK7RT61SV"
    assert mpesa_order.status == Order.Status.PAID and mpesa_order.paid_at is not None

    # Safaricom may deliver the same callback twice.
    assert APIClient().post(CALLBACK_PATH, stk_callback(checkout), format="json").status_code == 200
    assert Payment.objects.filter(order=mpesa_order, status=Payment.Status.SUCCESS).count() == 1


@responses.activate
def test_cancelled_prompt_allows_retry(farmer, mpesa_order):
    checkout = mock_stk_push("ws_CO_first")
    client = client_for(farmer)
    client.post(f"/api/v1/orders/{mpesa_order.id}/pay/", {"phone": "0712345678"}, format="json")
    APIClient().post(CALLBACK_PATH, stk_callback(checkout, result_code=1032), format="json")

    mpesa_order.refresh_from_db()
    assert mpesa_order.status == Order.Status.AWAITING_PAYMENT
    assert Payment.objects.get(checkout_request_id=checkout).status == Payment.Status.FAILED

    mock_stk_push("ws_CO_second")
    assert client.post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json").status_code == 202


@responses.activate
def test_second_prompt_while_one_is_open_is_rejected(farmer, mpesa_order):
    mock_stk_push()
    client = client_for(farmer)
    client.post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    response = client.post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    assert response.status_code == 409


@responses.activate
def test_wrong_amount_goes_to_review(farmer, mpesa_order):
    checkout = mock_stk_push()
    client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    APIClient().post(CALLBACK_PATH, stk_callback(checkout, amount=1), format="json")

    mpesa_order.refresh_from_db()
    assert Payment.objects.get(checkout_request_id=checkout).status == Payment.Status.REVIEW
    assert mpesa_order.status == Order.Status.AWAITING_PAYMENT


def test_callback_with_wrong_token_is_rejected(mpesa_order):
    response = APIClient().post(
        "/api/v1/payments/mpesa/callback/guess/", stk_callback("ws_CO_x"), format="json"
    )
    assert response.status_code == 404


def test_callback_for_unknown_checkout_is_acknowledged():
    response = APIClient().post(CALLBACK_PATH, stk_callback("ws_CO_unknown"), format="json")
    assert response.status_code == 200


def test_malformed_callback_is_400():
    assert APIClient().post(CALLBACK_PATH, {"hello": "world"}, format="json").status_code == 400


@responses.activate
def test_mpesa_outage_returns_503_and_records_failure(farmer, mpesa_order):
    responses.get(OAUTH_URL, json={"access_token": "t", "expires_in": "3599"})
    responses.post(STK_URL, status=500, json={"errorCode": "500.003.02", "errorMessage": "System is busy"})

    response = client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")

    assert response.status_code == 503
    assert Payment.objects.get(order=mpesa_order).status == Payment.Status.FAILED


def test_pay_requires_valid_phone(farmer, mpesa_order):
    response = client_for(farmer).post(
        f"/api/v1/orders/{mpesa_order.id}/pay/", {"phone": "12345"}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_phone"


def test_pay_without_callback_config_is_503(farmer, mpesa_order, settings):
    settings.MPESA = {**settings.MPESA, "CALLBACK_BASE_URL": ""}
    response = client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    assert response.status_code == 503


@responses.activate
def test_reconcile_resolves_payment_without_callback(farmer, mpesa_order):
    checkout = mock_stk_push()
    client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    Payment.objects.filter(checkout_request_id=checkout).update(
        created_at=timezone.now() - timedelta(minutes=3)
    )
    responses.post(
        QUERY_URL, json={"ResponseCode": "0", "ResultCode": "0", "ResultDesc": "processed successfully"}
    )

    assert services.reconcile_pending_payments() == 1

    mpesa_order.refresh_from_db()
    assert mpesa_order.status == Order.Status.PAID


@responses.activate
def test_reconcile_times_out_abandoned_prompt(farmer, mpesa_order):
    checkout = mock_stk_push()
    client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    Payment.objects.filter(checkout_request_id=checkout).update(
        created_at=timezone.now() - timedelta(minutes=30)
    )
    responses.post(
        QUERY_URL,
        status=500,
        json={"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"},
    )

    services.reconcile_pending_payments()

    assert Payment.objects.get(checkout_request_id=checkout).status == Payment.Status.FAILED


@responses.activate
def test_late_success_after_timeout_still_pays_order(farmer, mpesa_order):
    checkout = mock_stk_push()
    client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/pay/", {}, format="json")
    Payment.objects.filter(checkout_request_id=checkout).update(
        status=Payment.Status.FAILED, result_code="timeout"
    )

    APIClient().post(CALLBACK_PATH, stk_callback(checkout), format="json")

    mpesa_order.refresh_from_db()
    assert mpesa_order.status == Order.Status.PAID


def test_cancel_order(farmer, mpesa_order):
    response = client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/cancel/")
    assert response.status_code == 200 and response.json()["status"] == "cancelled"


def test_paid_order_cannot_be_cancelled(farmer, mpesa_order):
    Order.objects.filter(pk=mpesa_order.pk).update(status=Order.Status.PAID)
    assert client_for(farmer).post(f"/api/v1/orders/{mpesa_order.id}/cancel/").status_code == 409


def test_other_farmer_cannot_see_order(other_farmer, mpesa_order):
    assert client_for(other_farmer).get(f"/api/v1/orders/{mpesa_order.id}/").status_code == 404


# --- 5.3 Sale match at pickup ------------------------------------------------------


def sale_body(order, product_id=None):
    return {"prescription_code": order.prescription.code, "product_id": str(product_id or order.product_id)}


def test_sale_match_collects_paid_order(agrovet, mpesa_order):
    Order.objects.filter(pk=mpesa_order.pk).update(status=Order.Status.PAID, paid_at=timezone.now())

    response = client_for(agrovet.user).post(
        "/api/v1/agrovet/sales/match/", sale_body(mpesa_order), format="json"
    )

    assert response.status_code == 201 and response.json()["result"] == "verified"
    mpesa_order.refresh_from_db()
    assert mpesa_order.status == Order.Status.COLLECTED
    assert Case.objects.get(pk=mpesa_order.prescription.case_id).status == Case.Status.PURCHASED


def test_sale_match_mismatch_does_not_collect(agrovet, mpesa_order, unprescribed_product):
    Order.objects.filter(pk=mpesa_order.pk).update(status=Order.Status.PAID)

    response = client_for(agrovet.user).post(
        "/api/v1/agrovet/sales/match/", sale_body(mpesa_order, unprescribed_product.id), format="json"
    )

    assert response.json()["result"] == "mismatch"
    mpesa_order.refresh_from_db()
    assert mpesa_order.status == Order.Status.PAID


def test_sale_match_rejects_unpaid_mpesa_order(agrovet, mpesa_order):
    response = client_for(agrovet.user).post(
        "/api/v1/agrovet/sales/match/", sale_body(mpesa_order), format="json"
    )
    assert response.status_code == 409 and response.json()["code"] == "not_paid"


def test_pay_at_shop_is_paid_on_collection(farmer, agrovet, prescription, store_item):
    order = services.create_order(
        farmer=farmer,
        prescription=prescription,
        store_item_id=store_item.id,
        quantity=1,
        payment_method="pay_at_shop",
    )
    client_for(agrovet.user).post("/api/v1/agrovet/sales/match/", sale_body(order), format="json")
    order.refresh_from_db()
    assert order.status == Order.Status.COLLECTED and order.paid_at is not None


def test_other_store_cannot_match_sale(far_agrovet, mpesa_order):
    Order.objects.filter(pk=mpesa_order.pk).update(status=Order.Status.PAID)
    response = client_for(far_agrovet.user).post(
        "/api/v1/agrovet/sales/match/", sale_body(mpesa_order), format="json"
    )
    assert response.status_code == 404


def test_farmer_cannot_match_sales(farmer, mpesa_order):
    response = client_for(farmer).post("/api/v1/agrovet/sales/match/", sale_body(mpesa_order), format="json")
    assert response.json()["code"] == "agrovet_not_verified"


# --- 5.4 Label verification and 5.5 reward ---------------------------------------


@responses.activate
def test_verified_label_completes_case_and_rewards_farmer(farmer, agrovet, mpesa_order):
    order = collected_order(mpesa_order, agrovet)
    responses.post(
        OCR_URL, json=ocr_response("RIDOMIL GOLD MZ 68 WG\nReg No. PCPB(CR) 0856\nKeep away from children")
    )

    response = client_for(farmer).post(
        f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["result"] == "verified"
    assert body["product"]["name"] == "Ridomil Gold MZ 68 WG"
    assert Case.objects.get(pk=order.prescription.case_id).status == Case.Status.VERIFIED
    assert balance(farmer) == 10
    assert Verification.objects.get(pk=body["id"]).photo.name.endswith(".jpg")

    rewards = client_for(farmer).get("/api/v1/rewards/").json()
    assert rewards["balance"] == 10 and rewards["entries"][0]["reason"] == "verified_purchase"

    again = client_for(farmer).post(
        f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )
    assert again.status_code == 409
    assert balance(farmer) == 10


@responses.activate
def test_unregistered_label_flags_case(farmer, agrovet, mpesa_order):
    order = collected_order(mpesa_order, agrovet)
    responses.post(OCR_URL, json=ocr_response("SUPER BLIGHT KILLER\nPCPB(CR) 9999"))

    body = (
        client_for(farmer)
        .post(f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart")
        .json()
    )

    assert body["result"] == "not_registered"
    assert body["message"] == "Not a registered product. Do not use."
    assert Case.objects.get(pk=order.prescription.case_id).status == Case.Status.FLAGGED
    assert balance(farmer) == 0


@responses.activate
def test_registered_but_unprescribed_label(farmer, agrovet, mpesa_order, unprescribed_product):
    order = collected_order(mpesa_order, agrovet)
    responses.post(OCR_URL, json=ocr_response("DUDUTHRIN PCPB (CR) 0333"))

    body = (
        client_for(farmer)
        .post(f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart")
        .json()
    )

    assert body["result"] == "not_prescribed"


@responses.activate
def test_unreadable_label_can_be_retaken(farmer, agrovet, mpesa_order):
    order = collected_order(mpesa_order, agrovet)
    responses.post(OCR_URL, json=ocr_response("blurry text only"))
    responses.post(OCR_URL, json=ocr_response("PCPB(CR)0856"))
    client = client_for(farmer)

    first = client.post(
        f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )
    assert first.json()["result"] == "unreadable"
    assert Case.objects.get(pk=order.prescription.case_id).status == Case.Status.PURCHASED

    second = client.post(
        f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )
    assert second.json()["result"] == "verified"


def test_label_check_requires_collection(farmer, mpesa_order):
    response = client_for(farmer).post(
        f"/api/v1/orders/{mpesa_order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )
    assert response.status_code == 409


@responses.activate
def test_ocr_outage_returns_503(farmer, agrovet, mpesa_order):
    order = collected_order(mpesa_order, agrovet)
    responses.post(OCR_URL, status=503)
    response = client_for(farmer).post(
        f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart"
    )
    assert response.status_code == 503
    assert not Verification.objects.filter(order=order, type="label_check").exists()


@responses.activate
def test_flagged_farmer_is_redirected_to_another_store(
    farmer, agrovet, far_agrovet, mpesa_order, alt_product
):
    order = collected_order(mpesa_order, agrovet)
    responses.post(OCR_URL, json=ocr_response("PCPB(CR) 9999"))
    client = client_for(farmer)
    client.post(f"/api/v1/orders/{order.id}/label-check/", {"photo": label_photo()}, format="multipart")
    other_item = StoreItem.objects.create(agrovet=far_agrovet, product=alt_product, price_kes=400)
    code = order.prescription.code

    stores = client.get(f"/api/v1/prescriptions/{code}/stores/").json()
    assert [s["agrovet_name"] for s in stores] == ["Chogoria Farm Inputs"]

    blocked = client.post(
        "/api/v1/orders/",
        {
            "prescription_code": code,
            "store_item_id": str(order.store_item_id),
            "payment_method": "pay_at_shop",
        },
        format="json",
    )
    assert blocked.json()["code"] == "store_excluded"

    response = client.post(
        "/api/v1/orders/",
        {"prescription_code": code, "store_item_id": str(other_item.id), "payment_method": "pay_at_shop"},
        format="json",
    )
    assert response.status_code == 201
    assert Case.objects.get(pk=order.prescription.case_id).status == Case.Status.PRESCRIBED


@responses.activate
def test_repeated_failures_flag_the_store(agrovet, alt_product, product, settings):
    from apps.accounts.models import User
    from apps.prescriptions.models import Prescription

    settings.PURCHASES = {**settings.PURCHASES, "STORE_FLAG_THRESHOLD": 2}
    item = StoreItem.objects.create(agrovet=agrovet, product=product, price_kes=650)
    responses.post(OCR_URL, json=ocr_response("PCPB(CR) 9999"))

    for i in range(2):
        farmer = User.objects.create_user(username=f"f{i}", password="x")
        case = Case.objects.create(farmer=farmer, status=Case.Status.PRESCRIBED)
        prescription = Prescription.objects.create(
            case=case,
            approved_product=product,
            approved_by=agrovet,
            expires_at=timezone.now() + timedelta(days=3),
        )
        order = services.create_order(
            farmer=farmer,
            prescription=prescription,
            store_item_id=item.id,
            quantity=1,
            payment_method="pay_at_shop",
        )
        services.match_sale(agrovet_user=agrovet.user, code=prescription.code, product_id=product.id)
        order.refresh_from_db()
        services.label_check(farmer=farmer, order=order, photo=image_bytes())

    flag = StoreFlag.objects.get(agrovet=agrovet, resolved_at__isnull=True)
    assert flag.failed_checks == 2


# --- Expiry -------------------------------------------------------------------------


def test_unused_prescription_expires_and_reservation_is_cancelled(farmer, prescription, store_item):
    order = services.create_order(
        farmer=farmer,
        prescription=prescription,
        store_item_id=store_item.id,
        quantity=1,
        payment_method="pay_at_shop",
    )
    prescription.expires_at = timezone.now() - timedelta(minutes=1)
    prescription.save()

    assert services.expire_prescriptions() == 1

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert Case.objects.get(pk=prescription.case_id).status == Case.Status.EXPIRED


def test_paid_order_is_never_expired(farmer, mpesa_order):
    Order.objects.filter(pk=mpesa_order.pk).update(status=Order.Status.PAID)
    prescription = mpesa_order.prescription
    prescription.expires_at = timezone.now() - timedelta(minutes=1)
    prescription.save()

    assert services.expire_prescriptions() == 0
    assert Case.objects.get(pk=prescription.case_id).status == Case.Status.PRESCRIBED


# --- Store catalogue (store rules) ------------------------------------------------


def test_verified_agrovet_manages_catalogue(agrovet, alt_product, product):
    client = client_for(agrovet.user)
    created = client.post(
        "/api/v1/agrovet/store-items/", {"product_id": str(alt_product.id), "price_kes": 420}, format="json"
    )
    assert created.status_code == 201

    duplicate = client.post(
        "/api/v1/agrovet/store-items/", {"product_id": str(alt_product.id), "price_kes": 1}, format="json"
    )
    assert duplicate.status_code == 400

    item_id = created.json()["id"]
    assert (
        client.patch(
            f"/api/v1/agrovet/store-items/{item_id}/", {"in_stock": False}, format="json"
        ).status_code
        == 200
    )
    assert [i["product"]["name"] for i in client.get("/api/v1/agrovet/store-items/").json()] == [
        "Mancozeb 80 WP"
    ]


def test_inactive_product_cannot_be_listed(agrovet, alt_product):
    alt_product.is_active = False
    alt_product.save()
    response = client_for(agrovet.user).post(
        "/api/v1/agrovet/store-items/", {"product_id": str(alt_product.id), "price_kes": 420}, format="json"
    )
    assert response.status_code == 400


def test_unverified_agrovet_cannot_open_store(alt_product):
    pending = make_agrovet("agro9", name="New Shop", lat="-0.3", lng="37.6", status=Agrovet.Status.PENDING)
    response = client_for(pending.user).post(
        "/api/v1/agrovet/store-items/", {"product_id": str(alt_product.id), "price_kes": 420}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "agrovet_not_verified"


def test_agrovet_sees_orders_at_their_store(agrovet, far_agrovet, mpesa_order):
    assert [o["id"] for o in client_for(agrovet.user).get("/api/v1/orders/").json()] == [str(mpesa_order.id)]
    assert client_for(far_agrovet.user).get("/api/v1/orders/").json() == []
