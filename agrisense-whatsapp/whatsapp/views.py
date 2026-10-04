import hashlib
import hmac
import json
import logging
import threading

from django.conf import settings
from django.db import IntegrityError, close_old_connections
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from . import client as wa
from .flow import Incoming, handle
from .models import ProcessedMessage

log = logging.getLogger(__name__)


@csrf_exempt
def webhook(request):
    if request.method == "GET":
        return verify(request)
    if request.method != "POST":
        return HttpResponse(status=405)

    if not valid_signature(request):
        log.warning("Rejected webhook with bad signature")
        return HttpResponseForbidden("bad signature")

    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=400)

    for msg in parse_messages(payload):
        try:
            ProcessedMessage.objects.create(wamid=msg.wamid)
        except IntegrityError:
            continue  # duplicate delivery from Meta — already handled
        if settings.WA_ASYNC:
            threading.Thread(target=_process, args=(msg,), daemon=True).start()
        else:
            _process(msg)

    # Always answer 200 quickly, otherwise Meta keeps retrying.
    return HttpResponse("OK")


def verify(request):
    """Meta calls GET ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=... when you save the webhook."""
    if (request.GET.get("hub.mode") == "subscribe"
            and request.GET.get("hub.verify_token") == settings.WA_VERIFY_TOKEN):
        return HttpResponse(request.GET.get("hub.challenge", ""))
    return HttpResponseForbidden("verification failed")


def valid_signature(request):
    if not settings.WA_APP_SECRET:
        return True  # dev mode — set WA_APP_SECRET in production
    header = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(settings.WA_APP_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header, expected)


def parse_messages(payload):
    """Turn Meta's nested webhook JSON into a flat list of Incoming messages (status updates are ignored)."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                phone = m.get("from", "")
                msg = Incoming(phone=phone, wamid=m.get("id", ""), name=names.get(phone, ""))
                kind = m.get("type")
                if kind == "text":
                    msg.text = m.get("text", {}).get("body", "")
                elif kind == "interactive":
                    inter = m.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    msg.kind, msg.reply_id, msg.text = "reply", reply.get("id", ""), reply.get("title", "")
                elif kind == "button":  # quick-reply on a template message
                    btn = m.get("button", {})
                    msg.kind, msg.reply_id, msg.text = "reply", btn.get("payload", ""), btn.get("text", "")
                elif kind == "image":
                    img = m.get("image", {})
                    msg.kind, msg.media_id, msg.mime = "image", img.get("id", ""), img.get("mime_type", "image/jpeg")
                    msg.text = img.get("caption", "")
                elif kind == "document" and (m.get("document", {}).get("mime_type", "")).startswith("image/"):
                    doc = m["document"]
                    msg.kind, msg.media_id, msg.mime = "image", doc.get("id", ""), doc.get("mime_type")
                elif kind == "location":
                    loc = m.get("location", {})
                    msg.kind, msg.latitude, msg.longitude = "location", loc.get("latitude"), loc.get("longitude")
                else:
                    msg.kind = "other"
                if msg.phone and msg.wamid:
                    out.append(msg)
    return out


def _process(msg):
    try:
        if settings.WA_ASYNC:
            close_old_connections()
        wa.mark_read(msg.wamid)
        handle(msg)
    except Exception:  # never let one bad message kill the worker
        log.exception("Failed to handle message %s from %s", msg.wamid, msg.phone)
    finally:
        if settings.WA_ASYNC:
            close_old_connections()
