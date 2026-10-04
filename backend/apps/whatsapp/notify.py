"""System events delivered on WhatsApp to farmers who chat with AgriSense there.

Meta allows free-form messages only within 24 hours of the farmer's last message; outside
that window (or for farmers not on WhatsApp) these functions return False and the caller
falls back to SMS. Each event is sent at most once (OutboundMessage.source_ref).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import transport as wa
from .messages import text
from .models import Conversation

logger = logging.getLogger(__name__)

SERVICE_WINDOW = timedelta(hours=24)


def active_conversation(user) -> Conversation | None:
    """The farmer's WhatsApp conversation, if a free-form message can be sent to it now."""
    if user is None or not settings.WHATSAPP["ENABLED"]:
        return None
    conv = Conversation.objects.filter(user=user).first()
    if conv is None or conv.last_inbound_at is None:
        return None
    if timezone.now() - conv.last_inbound_at > SERVICE_WINDOW:
        return None
    return conv


def _language(user) -> str:
    from apps.cases.services import farmer_language

    return farmer_language(user)


def farmer_event(case, key: str, body: str, source_ref: str, values: dict) -> bool:
    """Deliver a notifications.events message on WhatsApp, with the buttons that fit it.

    ``body`` is the same text the farmer would get by SMS. Returns True if queued on WhatsApp.
    """
    conv = active_conversation(case.farmer)
    if conv is None:
        return False
    lang = _language(case.farmer)
    menu = ("MENU", text("btn_menu", lang))
    if key == "prescription" and values.get("code"):
        buttons = [(f"BUYRX:{values['code']}", text("btn_find_stores", lang)), menu]
    elif key.startswith("retake_"):
        buttons = [(f"RETAKE:{case.pk}", text("btn_retake", lang)), menu]
    else:
        buttons = [menu]
    wa.send_buttons(conv.phone, body, buttons, source_ref=f"event:{key}:{source_ref}")
    return True


def order_paid(order) -> bool:
    conv = active_conversation(order.farmer)
    if conv is None:
        return False
    lang = _language(order.farmer)
    receipt = order.payments.filter(status="success").values_list("mpesa_receipt", flat=True).first() or "-"
    wa.send_buttons(
        conv.phone,
        text(
            "paid",
            lang,
            receipt=receipt,
            product=order.product.name,
            agrovet=order.agrovet.name,
            code=order.prescription.code,
        ),
        [("MENU", text("btn_menu", lang))],
        source_ref=f"order_paid:{order.pk}",
    )
    return True


def payment_failed(payment) -> bool:
    order = payment.order
    conv = active_conversation(order.farmer)
    if conv is None:
        return False
    lang = _language(order.farmer)
    wa.send_buttons(
        conv.phone,
        text("payment_failed", lang, reason=payment.result_desc or payment.result_code or "-"),
        [(f"RETRYPAY:{order.pk}", text("btn_try_again", lang)), ("MENU", text("btn_menu", lang))],
        source_ref=f"payment_failed:{payment.pk}",
    )
    return True


def order_collected(order) -> bool:
    """After the agrovet's sale match, ask for the label photo and route the next photo to the check."""
    conv = Conversation.objects.select_for_update().filter(user=order.farmer).first()
    if conv is None or active_conversation(order.farmer) is None:
        return False
    lang = _language(order.farmer)
    conv.step, conv.data = "LABEL", {"order_id": str(order.pk)}
    conv.save(update_fields=["step", "data", "updated_at"])
    wa.send_text(
        conv.phone,
        text("label_prompt", lang, agrovet=order.agrovet.name, product=order.product.name),
        source_ref=f"order_collected:{order.pk}",
    )
    return True
