"""Web transport: instead of calling Meta, outgoing WhatsApp payloads are stored
and the /chat/ page picks them up. The payloads are the exact JSON the Cloud API
would receive, so the browser shows what a farmer would see on WhatsApp."""
from pathlib import Path

from django.conf import settings

from .models import WebMessage


def deliver(payload):
    if payload.get("status") == "read":
        return {"success": True}
    to = payload.get("to", "")
    msg = WebMessage.objects.create(phone=to, direction=WebMessage.OUT, payload=payload)
    return {"messages": [{"id": f"web.{msg.pk}"}]}


def read_upload(media_id):
    rel = media_id.split(":", 1)[1]
    path = (Path(settings.MEDIA_ROOT) / rel).resolve()
    if not str(path).startswith(str(Path(settings.MEDIA_ROOT).resolve())) or not path.is_file():
        return None, None
    mime = {"png": "image/png", "webp": "image/webp"}.get(path.suffix.lower().lstrip("."), "image/jpeg")
    return path.read_bytes(), mime


def push_stk(phone, order):
    """Show the M-Pesa PIN prompt on the farmer's screen (simulated STK push)."""
    WebMessage.objects.create(
        phone=phone,
        direction=WebMessage.STK,
        payload={
            "checkout_id": order.checkout_request_id,
            "amount": order.amount,
            "pay_phone": order.pay_phone,
            "merchant": "AGRISENSE HUB",
            "account": f"AGS{order.pk}",
        },
    )
