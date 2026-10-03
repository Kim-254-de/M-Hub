"""SMS outbox: queue in the business transaction, send after commit, track delivery."""

from __future__ import annotations

import enum
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.phone import normalize_kenyan_phone

from .integrations import africastalking as at
from .models import SmsMessage

logger = logging.getLogger(__name__)

# A SENDING row older than this belongs to a dead worker and may be reclaimed.
STALE_SENDING_AFTER = timedelta(minutes=5)

DELIVERED_STATUSES = {"Success", "Delivered"}
FAILED_STATUSES = {"Failed", "Rejected", "AbsentSubscriber", "Expired"}


class SendOutcome(enum.Enum):
    SENT = "sent"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


def queue_sms(*, to: str | None, body: str, purpose: str, source_ref: str) -> SmsMessage | None:
    """Queue an SMS once per (purpose, source_ref, recipient). Sent after the current transaction commits.

    Returns None when SMS is disabled, the number is missing or invalid, or the message was already queued.
    """
    from .tasks import send_sms_task

    if not settings.SMS["ENABLED"]:
        return None
    phone = normalize_kenyan_phone(to or "")
    if phone is None:
        logger.info("No valid phone for %s SMS (%s); not sent", purpose, source_ref)
        return None
    try:
        with transaction.atomic():
            message = SmsMessage.objects.create(to=phone, body=body, purpose=purpose, source_ref=source_ref)
    except IntegrityError:
        logger.info("%s SMS for %s already queued", purpose, source_ref)
        return None
    transaction.on_commit(lambda: send_sms_task.delay(str(message.id)))
    return message


def send_sms(message_id) -> SendOutcome:
    """Send a queued SMS. Idempotent: rows already sent or being sent elsewhere are skipped."""
    message = _claim(message_id)
    if message is None:
        return SendOutcome.SKIPPED
    try:
        result = at.AfricasTalkingClient.from_settings().send(to=message.to, message=message.body)
    except at.SmsError as exc:
        return _record_failure(message, exc)
    except Exception as exc:
        logger.exception("Unexpected error sending SMS %s", message.id)
        return _record_failure(message, at.SmsTemporaryError(f"{type(exc).__name__}: {exc}"))

    message.status = SmsMessage.Status.SENT
    message.provider_message_id = result.message_id or None
    message.provider_status = result.status[:32]
    message.cost = result.cost[:32]
    message.error = ""
    message.sent_at = timezone.now()
    message.save()
    logger.info("SMS %s (%s) sent: %s", message.id, message.purpose, result.message_id)
    return SendOutcome.SENT


def retry_delay_seconds(attempts: int) -> int:
    """Exponential backoff: 30s, 60s, 120s, ... capped at 30 minutes."""
    return min(30 * 2 ** max(attempts - 1, 0), 30 * 60)


def _claim(message_id) -> SmsMessage | None:
    stale_before = timezone.now() - STALE_SENDING_AFTER
    with transaction.atomic():
        message = SmsMessage.objects.select_for_update().filter(pk=message_id).first()
        if message is None:
            return None
        claimable = message.status == SmsMessage.Status.QUEUED or (
            message.status == SmsMessage.Status.SENDING and message.updated_at < stale_before
        )
        if not claimable:
            return None
        message.status = SmsMessage.Status.SENDING
        message.attempts += 1
        message.save(update_fields=["status", "attempts", "updated_at"])
    return message


def _record_failure(message: SmsMessage, exc: at.SmsError) -> SendOutcome:
    will_retry = exc.retryable and message.attempts < settings.SMS["MAX_ATTEMPTS"]
    message.error = str(exc)[:255]
    message.status = SmsMessage.Status.QUEUED if will_retry else SmsMessage.Status.FAILED
    message.save(update_fields=["status", "error", "updated_at"])
    if will_retry:
        logger.warning("SMS %s attempt %s failed: %s; will retry", message.id, message.attempts, exc)
        return SendOutcome.RETRY
    log = logger.error if isinstance(exc, at.SmsConfigError) or exc.status_code == 405 else logger.warning
    log("SMS %s (%s) to %s failed: %s", message.id, message.purpose, message.to, exc)
    return SendOutcome.FAILED


def handle_delivery_report(data) -> None:
    """Apply an Africa's Talking delivery report (form fields ``id``, ``status``, ``failureReason``)."""
    message_id = (data.get("id") or "").strip()
    status = (data.get("status") or "").strip()
    if not message_id or not status:
        raise ValueError("Delivery report needs id and status")
    message = SmsMessage.objects.filter(provider_message_id=message_id).first()
    if message is None:
        logger.warning("Delivery report for unknown SMS %s", message_id)
        return
    message.provider_status = status[:32]
    if status in DELIVERED_STATUSES:
        message.status = SmsMessage.Status.DELIVERED
        message.delivered_at = message.delivered_at or timezone.now()
    elif status in FAILED_STATUSES and message.status != SmsMessage.Status.DELIVERED:
        message.status = SmsMessage.Status.FAILED
        message.error = (data.get("failureReason") or status)[:255]
        logger.warning("SMS %s to %s not delivered: %s", message.id, message.to, message.error)
    message.save()
