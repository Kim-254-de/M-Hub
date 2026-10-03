"""Module 4: Buy Genuine Product (Documentation §6.4, §8.5)."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.agrovets.models import Agrovet, StoreItem
from apps.core.models import TimeStampedModel
from apps.prescriptions.models import Prescription
from apps.products.models import Product


def label_photo_upload_to(instance, filename):
    return f"label_checks/{instance.order_id}/{instance.id}.jpg"


class Order(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        MPESA = "mpesa", "M-Pesa (STK push)"
        PAY_AT_SHOP = "pay_at_shop", "Reserve and pay at shop"

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment"  # M-Pesa order not yet paid
        RESERVED = "reserved"  # pay-at-shop order held for pickup
        PAID = "paid"
        COLLECTED = "collected"  # sale matched to the prescription at pickup
        CANCELLED = "cancelled"

    ACTIVE_STATUSES = (Status.AWAITING_PAYMENT, Status.RESERVED, Status.PAID)

    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name="orders")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    agrovet = models.ForeignKey(Agrovet, on_delete=models.PROTECT, related_name="orders")
    store_item = models.ForeignKey(StoreItem, on_delete=models.SET_NULL, null=True, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="orders")
    # Price snapshot at order time, so later catalogue edits never change what the farmer owes.
    unit_price_kes = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    total_kes = models.PositiveIntegerField()
    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            # One open order per prescription: a prescription is bought once.
            models.UniqueConstraint(
                fields=["prescription"],
                condition=Q(status__in=["awaiting_payment", "reserved", "paid"]),
                name="purchases_one_active_order_per_prescription",
            ),
            models.CheckConstraint(
                condition=Q(total_kes=models.F("unit_price_kes") * models.F("quantity")),
                name="purchases_order_total_matches",
            ),
        ]
        indexes = [
            models.Index(fields=["farmer", "-created_at"]),
            models.Index(fields=["agrovet", "status"]),
        ]

    def __str__(self):
        return f"Order {self.id} ({self.status})"


class Payment(TimeStampedModel):
    """One M-Pesa STK push attempt for an order."""

    class Status(models.TextChoices):
        PENDING = "pending"  # prompt sent, waiting for the farmer / callback
        SUCCESS = "success"
        FAILED = "failed"  # cancelled, wrong PIN, insufficient funds, unreachable, expired
        REVIEW = "review"  # money received but amount or order state does not match; needs a human

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    amount_kes = models.PositiveIntegerField()
    phone = models.CharField(max_length=12, help_text="2547XXXXXXXX")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    merchant_request_id = models.CharField(max_length=64, blank=True)
    checkout_request_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    result_code = models.CharField(max_length=16, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    mpesa_receipt = models.CharField(max_length=32, unique=True, null=True, blank=True)
    raw_callback = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="pending"),
                name="purchases_one_pending_payment_per_order",
            ),
        ]

    def __str__(self):
        return f"Payment {self.id} KES {self.amount_kes} ({self.status})"


class Verification(TimeStampedModel):
    """Result of checking a purchase (§8.5 processes 5.3 and 5.4)."""

    class Type(models.TextChoices):
        SALE_MATCH = "sale_match"  # agrovet scans the prescription code at pickup
        LABEL_CHECK = "label_check"  # farmer photographs the product label

    class Result(models.TextChoices):
        VERIFIED = "verified"
        MISMATCH = "mismatch"  # sale match: product handed over is not the ordered/prescribed one
        NOT_REGISTERED = "not_registered"  # label check: number not in the PCPB register
        NOT_PRESCRIBED = "not_prescribed"  # label check: registered, but not prescribed for this case
        UNREADABLE = "unreadable"  # label check: no PCPB number could be read; farmer retakes

    FAILED_LABEL_RESULTS = (Result.NOT_REGISTERED, Result.NOT_PRESCRIBED)

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="verifications")
    type = models.CharField(max_length=16, choices=Type.choices)
    result = models.CharField(max_length=16, choices=Result.choices, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Product identified",
    )
    detected_reg_no = models.CharField(max_length=64, blank=True)
    photo = models.ImageField(upload_to=label_photo_upload_to, null=True, blank=True)
    ocr_text = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["order", "type", "-created_at"])]

    def __str__(self):
        return f"{self.type} {self.result} for order {self.order_id}"


class StoreFlag(TimeStampedModel):
    """Opened when one store accumulates failed label checks (§6.4 store rules)."""

    agrovet = models.ForeignKey(Agrovet, on_delete=models.PROTECT, related_name="flags")
    reason = models.CharField(max_length=255)
    failed_checks = models.PositiveIntegerField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["agrovet"],
                condition=Q(resolved_at__isnull=True),
                name="purchases_one_open_flag_per_store",
            ),
        ]

    def __str__(self):
        return f"Flag on {self.agrovet} ({'open' if self.resolved_at is None else 'resolved'})"
