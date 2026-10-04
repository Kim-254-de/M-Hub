"""Turning webhook payloads into stored InboundMessage rows."""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.accounts.phone import normalize_kenyan_phone

from .models import InboundMessage

logger = logging.getLogger(__name__)


def valid_signature(body: bytes, header: str) -> bool:
    """Meta signs every webhook with the app secret (X-Hub-Signature-256). Fails closed without a secret."""
    secret = settings.WHATSAPP["APP_SECRET"]
    if not secret:
        logger.error("WHATSAPP_APP_SECRET is not set; rejecting webhook")
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header or "", expected)


def _decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.000001")) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def parse(payload: dict) -> list[dict]:
    """Flatten Meta's webhook JSON into message dicts. Status updates (sent/delivered/read) are skipped."""
    out = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts") or []
            }
            for m in value.get("messages") or []:
                sender = m.get("from", "")
                phone = normalize_kenyan_phone(sender)
                if phone is None or not m.get("id"):
                    logger.warning("Ignoring WhatsApp message from unsupported number %s", sender)
                    continue
                item = {"wamid": m["id"], "phone": phone, "profile_name": names.get(sender, "")[:100]}
                kind = m.get("type")
                if kind == "text":
                    item.update(kind="text", text=(m.get("text") or {}).get("body", ""))
                elif kind == "interactive":
                    inter = m.get("interactive") or {}
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    item.update(kind="reply", reply_id=reply.get("id", ""), text=reply.get("title", ""))
                elif kind == "button":  # quick reply on a template message
                    btn = m.get("button") or {}
                    item.update(kind="reply", reply_id=btn.get("payload", ""), text=btn.get("text", ""))
                elif kind == "image" or (
                    kind == "document" and (m.get("document") or {}).get("mime_type", "").startswith("image/")
                ):
                    media = m.get(kind) or {}
                    item.update(
                        kind="image",
                        media_id=media.get("id", ""),
                        mime_type=media.get("mime_type", ""),
                        text=media.get("caption", ""),
                    )
                elif kind == "location":
                    loc = m.get("location") or {}
                    item.update(
                        kind="location",
                        latitude=_decimal(loc.get("latitude")),
                        longitude=_decimal(loc.get("longitude")),
                    )
                else:
                    item.update(kind="other")
                out.append(item)
    return out


def store(item: dict) -> InboundMessage | None:
    """Save one message and queue it for handling. Returns None for a repeated delivery."""
    from .tasks import process_inbound_task

    try:
        with transaction.atomic():
            message = InboundMessage.objects.create(**item)
    except IntegrityError:
        logger.info("Duplicate WhatsApp delivery %s ignored", item.get("wamid"))
        return None
    transaction.on_commit(lambda: process_inbound_task.delay(str(message.id)))
    return message
