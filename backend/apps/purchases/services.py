"""Module 4: Buy Genuine Product — business rules (Documentation §6.4, §8.5).

5.1 find_stores        5.2 create_order / initiate_payment / handle_stk_callback
5.3 match_sale         5.4 label_check        5.5 reward on verified purchase
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.cases.services import transition
from apps.prescriptions.models import Prescription
from apps.products.models import Product
from apps.products.pcpb import extract_keys
from apps.rewards.models import RewardEntry
from apps.rewards.services import award

from .integrations import mpesa, ocr
from .models import Order, Payment, StoreFlag, Verification

logger = logging.getLogger(__name__)

PURCHASABLE_CASE_STATUSES = (Case.Status.PRESCRIBED, Case.Status.FLAGGED)
FINAL_LABEL_RESULTS = (
    Verification.Result.VERIFIED,
    Verification.Result.NOT_REGISTERED,
    Verification.Result.NOT_PRESCRIBED,
)


# --- Errors -------------------------------------------------------------------


class PurchaseError(Exception):
    """A rule was broken by the request. ``status`` is the HTTP status the API returns."""

    status = 400

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class PurchaseNotFound(PurchaseError):
    status = 404


class PurchaseConflict(PurchaseError):
    status = 409


class PurchaseUnavailable(PurchaseError):
    """An external service (M-Pesa, OCR) is down or not configured. Safe to retry later."""

    status = 503


# --- Lookups ------------------------------------------------------------------


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def get_prescription_for_farmer(farmer, code: str) -> Prescription:
    prescription = (
        Prescription.objects.select_related("case", "approved_product")
        .filter(code=normalize_code(code), case__farmer=farmer)
        .first()
    )
    if prescription is None:
        raise PurchaseNotFound("No prescription with this code.", code="prescription_not_found")
    return prescription


def get_verified_agrovet(user) -> Agrovet:
    agrovet = getattr(user, "agrovet", None)
    if agrovet is None or not agrovet.is_verified:
        raise PurchaseError("Only verified agrovets can do this.", code="agrovet_not_verified")
    return agrovet


def _agrovets_failed_for(prescription: Prescription) -> set:
    """Stores whose product failed the label check for this prescription; the farmer is sent elsewhere."""
    return set(
        Verification.objects.filter(
            order__prescription=prescription,
            type=Verification.Type.LABEL_CHECK,
            result__in=Verification.FAILED_LABEL_RESULTS,
        ).values_list("order__agrovet_id", flat=True)
    )


def _ensure_purchasable(prescription: Prescription) -> None:
    if prescription.is_expired:
        raise PurchaseError("This prescription has expired.", code="prescription_expired")
    if prescription.case.status not in PURCHASABLE_CASE_STATUSES:
        raise PurchaseConflict(
            f"This case is {prescription.case.status} and cannot be ordered against.",
            code="case_not_purchasable",
        )


# --- 5.1 Find verified stores -------------------------------------------------


@dataclass(frozen=True)
class StoreOffer:
    store_item: StoreItem
    distance_km: float | None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def find_stores(
    prescription: Prescription, *, latitude=None, longitude=None, radius_km: float | None = None
) -> list[StoreOffer]:
    """Verified stores with a prescribed product in stock, nearest first, then cheapest."""
    _ensure_purchasable(prescription)
    config = settings.PURCHASES
    radius_km = radius_km or config["DEFAULT_STORE_RADIUS_KM"]
    if latitude is None or longitude is None:
        latitude, longitude = prescription.case.latitude, prescription.case.longitude

    items = (
        StoreItem.objects.select_related("agrovet", "product")
        .filter(
            product_id__in=prescription.purchasable_product_ids(),
            product__is_active=True,
            in_stock=True,
            agrovet__status=Agrovet.Status.VERIFIED,
        )
        .exclude(agrovet_id__in=_agrovets_failed_for(prescription))
    )

    offers = []
    for item in items:
        distance = None
        if latitude is not None and longitude is not None:
            distance = round(
                _haversine_km(latitude, longitude, item.agrovet.latitude, item.agrovet.longitude), 2
            )
            if distance > radius_km:
                continue
        offers.append(StoreOffer(store_item=item, distance_km=distance))

    offers.sort(
        key=lambda o: (o.distance_km if o.distance_km is not None else math.inf, o.store_item.price_kes)
    )
    return offers[: config["MAX_STORE_RESULTS"]]


# --- 5.2 Order and pay --------------------------------------------------------


def create_order(
    *, farmer, prescription: Prescription, store_item_id, quantity: int, payment_method: str
) -> Order:
    _ensure_purchasable(prescription)
    if payment_method not in Order.PaymentMethod.values:
        raise PurchaseError("Unknown payment method.", code="invalid_payment_method")

    item = StoreItem.objects.select_related("agrovet", "product").filter(pk=store_item_id).first()
    if item is None:
        raise PurchaseNotFound("Store item not found.", code="store_item_not_found")
    if not item.agrovet.is_verified:
        raise PurchaseError("This store is not a verified agrovet.", code="store_not_verified")
    if not item.in_stock or not item.product.is_active:
        raise PurchaseError("This product is not available at this store.", code="out_of_stock")
    if item.product_id not in prescription.purchasable_product_ids():
        raise PurchaseError("This product is not on your prescription.", code="product_not_prescribed")
    if item.agrovet_id in _agrovets_failed_for(prescription):
        raise PurchaseError(
            "A product from this store failed verification. Please choose another store.",
            code="store_excluded",
        )

    status = (
        Order.Status.AWAITING_PAYMENT
        if payment_method == Order.PaymentMethod.MPESA
        else Order.Status.RESERVED
    )
    try:
        with transaction.atomic():
            order = Order.objects.create(
                prescription=prescription,
                farmer=farmer,
                agrovet=item.agrovet,
                store_item=item,
                product=item.product,
                unit_price_kes=item.price_kes,
                quantity=quantity,
                total_kes=item.price_kes * quantity,
                payment_method=payment_method,
                status=status,
            )
            # FLAGGED -> PRESCRIBED: the farmer has been redirected to another verified store.
            transition(prescription.case_id, from_statuses=[Case.Status.FLAGGED], to=Case.Status.PRESCRIBED)
    except IntegrityError as exc:
        raise PurchaseConflict(
            "This prescription already has an open order. Cancel it first.", code="order_exists"
        ) from exc

    logger.info("Order %s created: %s x%s via %s", order.id, item.product.name, quantity, payment_method)
    return order


def cancel_order(*, farmer, order: Order) -> Order:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk, farmer=farmer)
        if order.status not in (Order.Status.AWAITING_PAYMENT, Order.Status.RESERVED):
            raise PurchaseConflict(f"A {order.status} order cannot be cancelled.", code="not_cancellable")
        if order.payments.filter(status=Payment.Status.PENDING).exists():
            raise PurchaseConflict(
                "An M-Pesa payment is still in progress. Try again in a minute.", code="payment_in_progress"
            )
        order.status = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_at", "updated_at"])
    return order


def _callback_url() -> str:
    config = settings.MPESA
    if not config["CALLBACK_BASE_URL"] or not config["CALLBACK_TOKEN"]:
        raise PurchaseUnavailable("M-Pesa payments are not configured.", code="mpesa_not_configured")
    path = reverse("v1:mpesa-callback", kwargs={"token": config["CALLBACK_TOKEN"]})
    return config["CALLBACK_BASE_URL"].rstrip("/") + path


def initiate_payment(*, farmer, order: Order, phone: str) -> Payment:
    """Send an STK push to the farmer's phone for the order total."""
    if order.farmer_id != farmer.pk:
        raise PurchaseNotFound("Order not found.", code="order_not_found")
    if order.payment_method != Order.PaymentMethod.MPESA or order.status != Order.Status.AWAITING_PAYMENT:
        raise PurchaseConflict("This order is not awaiting M-Pesa payment.", code="not_awaiting_payment")
    try:
        msisdn = mpesa.normalize_phone(phone)
    except ValueError as exc:
        raise PurchaseError(str(exc), code="invalid_phone") from exc

    callback_url = _callback_url()
    try:
        client = mpesa.MpesaClient.from_settings()
    except mpesa.MpesaConfigError as exc:
        logger.error("M-Pesa misconfigured: %s", exc)
        raise PurchaseUnavailable("M-Pesa payments are not configured.", code="mpesa_not_configured") from exc

    try:
        with transaction.atomic():
            payment = Payment.objects.create(order=order, amount_kes=order.total_kes, phone=msisdn)
    except IntegrityError as exc:
        raise PurchaseConflict(
            "A payment prompt is already open on your phone. Complete or cancel it first.",
            code="payment_in_progress",
        ) from exc

    try:
        response = client.stk_push(
            phone=msisdn,
            amount=order.total_kes,
            account_reference=order.prescription.code,
            description="AgriSense",
            callback_url=callback_url,
        )
    except mpesa.MpesaError as exc:
        payment.status = Payment.Status.FAILED
        payment.result_code = exc.error_code or "request_failed"
        payment.result_desc = str(exc)[:255]
        payment.completed_at = timezone.now()
        payment.save(update_fields=["status", "result_code", "result_desc", "completed_at", "updated_at"])
        if isinstance(exc, mpesa.MpesaConfigError):
            logger.error("M-Pesa credentials rejected: %s", exc)
        else:
            logger.warning("STK push for order %s failed: %s", order.id, exc)
        if exc.retryable or isinstance(exc, mpesa.MpesaConfigError):
            raise PurchaseUnavailable(
                "M-Pesa is not responding. Please try again shortly.", code="mpesa_unavailable"
            ) from exc
        raise PurchaseError("M-Pesa could not send the payment prompt.", code="mpesa_rejected") from exc

    payment.merchant_request_id = response.merchant_request_id
    payment.checkout_request_id = response.checkout_request_id
    payment.save(update_fields=["merchant_request_id", "checkout_request_id", "updated_at"])
    logger.info("STK push sent for order %s (checkout %s)", order.id, response.checkout_request_id)
    return payment


def handle_stk_callback(payload: dict) -> None:
    """Apply a Daraja STK callback. Idempotent; unknown or repeated callbacks are ignored."""
    data = mpesa.parse_stk_callback(payload)
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .select_related("order")
            .filter(checkout_request_id=data["checkout_request_id"])
            .first()
        )
        if payment is None:
            logger.warning("STK callback for unknown checkout %s", data["checkout_request_id"])
            return
        payment.raw_callback = payload
        _apply_payment_result(
            payment,
            result_code=data["result_code"],
            result_desc=data["result_desc"],
            amount=data["amount"],
            receipt=data["mpesa_receipt"],
        )


def _apply_payment_result(payment: Payment, *, result_code: str, result_desc: str, amount=None, receipt=None):
    """Must run inside a transaction with ``payment`` locked."""
    success = result_code == "0"
    late_success = payment.status == Payment.Status.FAILED and success
    if payment.status != Payment.Status.PENDING and not late_success:
        logger.info("Ignoring repeated result for payment %s (%s)", payment.id, payment.status)
        return

    payment.result_code = result_code
    payment.result_desc = result_desc[:255]
    payment.completed_at = timezone.now()
    if receipt:
        payment.mpesa_receipt = str(receipt)

    if not success:
        payment.status = Payment.Status.FAILED
        payment.save()
        logger.info("Payment %s failed: %s %s", payment.id, result_code, result_desc)
        return

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    amount_ok = amount is None or int(float(amount)) == payment.amount_kes
    if amount_ok and order.status == Order.Status.AWAITING_PAYMENT:
        payment.status = Payment.Status.SUCCESS
        payment.save()
        order.status = Order.Status.PAID
        order.paid_at = payment.completed_at
        order.save(update_fields=["status", "paid_at", "updated_at"])
        logger.info("Order %s paid (receipt %s)", order.id, payment.mpesa_receipt)
    else:
        # Money arrived but cannot be applied (wrong amount, or the order was cancelled/paid meanwhile).
        payment.status = Payment.Status.REVIEW
        payment.save()
        logger.error(
            "Payment %s needs review: amount=%s expected=%s order_status=%s receipt=%s",
            payment.id,
            amount,
            payment.amount_kes,
            order.status,
            payment.mpesa_receipt,
        )


def reconcile_pending_payments() -> int:
    """Ask Daraja about STK payments whose callback never arrived. Returns how many were resolved."""
    config = settings.PURCHASES
    now = timezone.now()
    pending = Payment.objects.filter(
        status=Payment.Status.PENDING,
        checkout_request_id__isnull=False,
        created_at__lt=now - timedelta(seconds=config["PAYMENT_RECONCILE_AFTER_SECONDS"]),
    ).order_by("created_at")[:50]
    if not pending:
        return 0

    try:
        client = mpesa.MpesaClient.from_settings()
    except mpesa.MpesaConfigError:
        logger.error("Cannot reconcile payments: M-Pesa is not configured")
        return 0

    resolved = 0
    timeout_before = now - timedelta(minutes=config["PAYMENT_TIMEOUT_MINUTES"])
    for payment in pending:
        try:
            result = client.stk_query(payment.checkout_request_id)
        except mpesa.MpesaError as exc:
            logger.warning("STK query for payment %s failed: %s", payment.id, exc)
            continue
        with transaction.atomic():
            locked = Payment.objects.select_for_update().get(pk=payment.pk)
            if result.pending:
                if locked.created_at < timeout_before:
                    _apply_payment_result(
                        locked, result_code="timeout", result_desc="No response from M-Pesa"
                    )
                    resolved += 1
                continue
            _apply_payment_result(locked, result_code=result.result_code, result_desc=result.result_desc)
            resolved += 1
    return resolved


# --- 5.3 Match sale to prescription at pickup ---------------------------------


def match_sale(*, agrovet_user, code: str, product_id) -> Verification:
    """The agrovet scans the prescription code and records the product handed over."""
    agrovet = get_verified_agrovet(agrovet_user)
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .select_related("prescription")
            .filter(
                prescription__code=normalize_code(code),
                agrovet=agrovet,
                status__in=[Order.Status.PAID, Order.Status.RESERVED, Order.Status.AWAITING_PAYMENT],
            )
            .first()
        )
        if order is None:
            raise PurchaseNotFound(
                "No open order for this prescription at your store.", code="order_not_found"
            )
        if order.status == Order.Status.AWAITING_PAYMENT:
            raise PurchaseConflict("The M-Pesa payment for this order is not complete.", code="not_paid")

        matches = str(product_id) == str(order.product_id)
        verification = Verification.objects.create(
            order=order,
            type=Verification.Type.SALE_MATCH,
            result=Verification.Result.VERIFIED if matches else Verification.Result.MISMATCH,
            actor=agrovet_user,
            product=Product.objects.filter(pk=product_id).first(),
        )
        if not matches:
            logger.warning(
                "Sale mismatch on order %s: sold %s, ordered %s", order.id, product_id, order.product_id
            )
            return verification

        now = timezone.now()
        order.status = Order.Status.COLLECTED
        order.collected_at = now
        order.paid_at = order.paid_at or now  # pay-at-shop: paid at the counter
        order.save(update_fields=["status", "collected_at", "paid_at", "updated_at"])
        transition(
            order.prescription.case_id, from_statuses=[Case.Status.PRESCRIBED], to=Case.Status.PURCHASED
        )
    logger.info("Order %s collected at %s", order.id, agrovet.name)
    return verification


# --- 5.4 Label verification ---------------------------------------------------


def label_check(*, farmer, order: Order, photo: bytes) -> Verification:
    """Read the PCPB number off the label photo and check it against the register and prescription."""
    if order.farmer_id != farmer.pk:
        raise PurchaseNotFound("Order not found.", code="order_not_found")
    if order.status != Order.Status.COLLECTED:
        raise PurchaseConflict("Collect the product before checking its label.", code="not_collected")
    if order.verifications.filter(
        type=Verification.Type.LABEL_CHECK, result__in=FINAL_LABEL_RESULTS
    ).exists():
        raise PurchaseConflict("This purchase has already been checked.", code="already_checked")
    if len(photo) > settings.PURCHASES["MAX_LABEL_PHOTO_BYTES"]:
        raise PurchaseError("The photo is too large.", code="photo_too_large")

    try:
        client = ocr.OcrSpaceClient.from_settings()
        image = ocr.prepare_image(photo, max_bytes=settings.OCR["MAX_UPLOAD_BYTES"])
        text = client.read_text(image)
    except ocr.OcrImageError as exc:
        raise PurchaseError(str(exc), code="invalid_photo") from exc
    except ocr.OcrConfigError as exc:
        logger.error("OCR misconfigured: %s", exc)
        raise PurchaseUnavailable(
            "Label checking is temporarily unavailable.", code="ocr_unavailable"
        ) from exc
    except ocr.OcrError as exc:
        logger.warning("OCR failed for order %s: %s", order.id, exc)
        raise PurchaseUnavailable(
            "Label checking is temporarily unavailable. Please try again.", code="ocr_unavailable"
        ) from exc

    keys = extract_keys(text)
    result, product = _classify_label(order, keys)

    with transaction.atomic():
        verification = Verification(
            order=order,
            type=Verification.Type.LABEL_CHECK,
            result=result,
            actor=farmer,
            product=product,
            detected_reg_no=", ".join(keys)[:64],
            ocr_text=text[:5000],
        )
        verification.photo.save("label.jpg", ContentFile(image), save=False)
        verification.save()

        case_id = order.prescription.case_id
        if result == Verification.Result.VERIFIED:
            transition(case_id, from_statuses=[Case.Status.PURCHASED], to=Case.Status.VERIFIED)
            award(
                farmer=farmer,
                reason=RewardEntry.Reason.VERIFIED_PURCHASE,
                points=settings.PURCHASES["REWARD_POINTS_VERIFIED_PURCHASE"],
                source_ref=f"order:{order.id}",
            )
        elif result in Verification.FAILED_LABEL_RESULTS:
            transition(case_id, from_statuses=[Case.Status.PURCHASED], to=Case.Status.FLAGGED)
            _maybe_flag_store(order.agrovet)

    log = logger.warning if result in Verification.FAILED_LABEL_RESULTS else logger.info
    log("Label check for order %s: %s (detected %s)", order.id, result, keys or "nothing")
    return verification


def _classify_label(order: Order, keys: list[str]) -> tuple[str, Product | None]:
    if not keys:
        return Verification.Result.UNREADABLE, None
    # A cancelled registration counts as not registered.
    registered = list(Product.objects.filter(pcpb_key__in=keys, is_active=True))
    if not registered:
        return Verification.Result.NOT_REGISTERED, None
    purchasable = order.prescription.purchasable_product_ids()
    for product in registered:
        if product.id in purchasable:
            return Verification.Result.VERIFIED, product
    return Verification.Result.NOT_PRESCRIBED, registered[0]


def _maybe_flag_store(agrovet: Agrovet) -> None:
    config = settings.PURCHASES
    since = timezone.now() - timedelta(days=config["STORE_FLAG_WINDOW_DAYS"])
    failed = Verification.objects.filter(
        order__agrovet=agrovet,
        type=Verification.Type.LABEL_CHECK,
        result__in=Verification.FAILED_LABEL_RESULTS,
        created_at__gte=since,
    ).count()
    if failed < config["STORE_FLAG_THRESHOLD"]:
        return
    try:
        with transaction.atomic():
            StoreFlag.objects.create(
                agrovet=agrovet,
                failed_checks=failed,
                reason=f"{failed} failed label checks in {config['STORE_FLAG_WINDOW_DAYS']} days",
            )
    except IntegrityError:
        StoreFlag.objects.filter(agrovet=agrovet, resolved_at__isnull=True).update(
            failed_checks=failed, updated_at=timezone.now()
        )
        return
    logger.warning("Store %s flagged after %s failed label checks", agrovet.id, failed)


# --- Prescription expiry (PRESCRIBED -> EXPIRED) ------------------------------


def expire_prescriptions() -> int:
    """Expire cases whose prescription ran out unused. Paid orders are never expired."""
    expired = 0
    prescriptions = Prescription.objects.filter(
        expires_at__lte=timezone.now(), case__status__in=PURCHASABLE_CASE_STATUSES
    ).select_related("case")
    for prescription in prescriptions:
        with transaction.atomic():
            open_orders = Order.objects.select_for_update().filter(
                prescription=prescription, status__in=Order.ACTIVE_STATUSES
            )
            if any(o.status == Order.Status.PAID for o in open_orders):
                continue
            if Payment.objects.filter(
                order__prescription=prescription, status=Payment.Status.PENDING
            ).exists():
                continue
            open_orders.update(
                status=Order.Status.CANCELLED, cancelled_at=timezone.now(), updated_at=timezone.now()
            )
            if transition(
                prescription.case_id, from_statuses=PURCHASABLE_CASE_STATUSES, to=Case.Status.EXPIRED
            ):
                expired += 1
    if expired:
        logger.info("Expired %s prescriptions", expired)
    return expired
