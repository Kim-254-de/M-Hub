import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import transport as wa
from .messages import text
from .models import Conversation, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=5)


def _claim(model, pk, waiting_status, working_status):
    """Move a row from waiting to working under a lock; reclaim rows abandoned by a dead worker."""
    with transaction.atomic():
        row = model.objects.select_for_update().filter(pk=pk).first()
        if row is None:
            return None
        stale = row.status == working_status and row.updated_at < timezone.now() - STALE_AFTER
        if row.status != waiting_status and not stale:
            return None
        row.status = working_status
        row.attempts += 1
        row.save(update_fields=["status", "attempts", "updated_at"])
    return row


@shared_task(bind=True, max_retries=None, acks_late=True, ignore_result=True)
def process_inbound_task(self, message_id: str) -> None:
    """Handle one farmer message. The conversation row is locked, so one farmer's messages run in order."""
    from .flow import Ctx, handle

    message = _claim(
        InboundMessage, message_id, InboundMessage.Status.RECEIVED, InboundMessage.Status.PROCESSING
    )
    if message is None:
        return
    wa.mark_read(message.wamid)
    try:
        with transaction.atomic():
            Conversation.objects.get_or_create(phone=message.phone)
            conversation = (
                Conversation.objects.select_for_update().select_related("user").get(phone=message.phone)
            )
            handle(Ctx(conversation=conversation, message=message))
            message.status, message.error = InboundMessage.Status.DONE, ""
            message.save(update_fields=["status", "error", "updated_at"])
    except Exception as exc:
        logger.exception("Handling WhatsApp message %s failed (attempt %s)", message.id, message.attempts)
        retry = message.attempts < settings.WHATSAPP["MAX_ATTEMPTS"]
        message.status = InboundMessage.Status.RECEIVED if retry else InboundMessage.Status.FAILED
        message.error = f"{type(exc).__name__}: {exc}"[:2000]
        message.save(update_fields=["status", "error", "updated_at"])
        if retry:
            raise self.retry(countdown=min(10 * 2 ** (message.attempts - 1), 300)) from exc
        with transaction.atomic():
            wa.send_text(message.phone, text("error", "en"))


@shared_task(bind=True, max_retries=None, acks_late=True, ignore_result=True)
def send_outbound_task(self, message_id: str) -> None:
    message = _claim(
        OutboundMessage, message_id, OutboundMessage.Status.QUEUED, OutboundMessage.Status.SENDING
    )
    if message is None:
        return
    try:
        provider_id = wa.CloudClient.from_settings().send(message.phone, message.payload)
    except wa.WhatsAppError as exc:
        retry = exc.retryable and message.attempts < settings.WHATSAPP["MAX_ATTEMPTS"]
        message.status = OutboundMessage.Status.QUEUED if retry else OutboundMessage.Status.FAILED
        message.error = str(exc)[:2000]
        message.save(update_fields=["status", "error", "updated_at"])
        log = logger.error if isinstance(exc, wa.WhatsAppConfigError) else logger.warning
        log("WhatsApp send %s to %s failed: %s", message.id, message.phone, exc)
        if retry:
            raise self.retry(countdown=min(15 * 2 ** (message.attempts - 1), 600)) from exc
        return
    message.status, message.provider_message_id, message.error = OutboundMessage.Status.SENT, provider_id, ""
    message.save(update_fields=["status", "provider_message_id", "error", "updated_at"])
