import hmac
import json
import logging
import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.phone import normalize_kenyan_phone

from . import inbound
from .models import Conversation, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


# --- Meta webhook -------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    config = settings.WHATSAPP
    if not config["ENABLED"] or config["TRANSPORT"] != "cloud":
        raise Http404
    if request.method == "GET":
        # Meta's verification handshake when the webhook URL is saved.
        token = request.GET.get("hub.verify_token", "")
        if (
            request.GET.get("hub.mode") == "subscribe"
            and config["VERIFY_TOKEN"]
            and hmac.compare_digest(token, config["VERIFY_TOKEN"])
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden("verification failed")

    if not inbound.valid_signature(request.body, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning(
            "Rejected WhatsApp webhook with a bad signature from %s", request.META.get("REMOTE_ADDR")
        )
        return HttpResponseForbidden("bad signature")
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=400)
    for item in inbound.parse(payload):
        inbound.store(item)
    # Answer quickly; handling happens in Celery. Meta retries anything that is not a 200.
    return HttpResponse("OK")


# --- Development simulator (WHATSAPP_TRANSPORT=web) ---------------------------------


def _simulator_only():
    config = settings.WHATSAPP
    if not (config["SIMULATOR_ENABLED"] and config["TRANSPORT"] == "web"):
        raise Http404("The WhatsApp simulator is off")


def _phone(raw):
    return normalize_kenyan_phone(raw or "")


def _cursor(dt) -> int:
    return int(dt.timestamp() * 1_000_000)


@require_GET
def simulator_page(request):
    _simulator_only()
    phone = _phone(request.GET.get("farmer")) or "+254712345678"
    return render(
        request,
        "whatsapp/simulator.html",
        {
            "farmer_phone": phone.lstrip("+"),
            "farmer_name": request.GET.get("name", "Peter Kamau")[:60],
            "agrovet_phone": "",
            "agrovet_name": "",
            "single": request.GET.get("single") == "1",
        },
    )


@csrf_exempt
@require_POST
def simulator_send(request):
    _simulator_only()
    phone = _phone(request.POST.get("phone"))
    if phone is None:
        return JsonResponse({"error": "Enter a valid Kenyan mobile number"}, status=400)
    item = {
        "wamid": f"sim.{uuid.uuid4().hex}",
        "phone": phone,
        "profile_name": request.POST.get("name", "")[:100],
    }
    image = request.FILES.get("image")
    if image:
        if image.size > settings.DETECT["MAX_PHOTO_BYTES"] or not (image.content_type or "").startswith(
            "image/"
        ):
            return JsonResponse({"error": "Please send a photo under 10 MB."}, status=400)
        name = default_storage.save(f"whatsapp/sim/{uuid.uuid4().hex}.jpg", image)
        item.update(
            kind="image",
            media_id=f"sim:{name}",
            mime_type=image.content_type,
            text=request.POST.get("text", "")[:500],
        )
    elif request.POST.get("reply_id"):
        item.update(
            kind="reply", reply_id=request.POST["reply_id"][:200], text=request.POST.get("title", "")[:100]
        )
    elif request.POST.get("latitude") and request.POST.get("longitude"):
        item.update(
            kind="location",
            latitude=inbound._decimal(request.POST["latitude"]),
            longitude=inbound._decimal(request.POST["longitude"]),
        )
    else:
        typed = request.POST.get("text", "").strip()
        if not typed:
            return JsonResponse({"error": "empty"}, status=400)
        item.update(kind="text", text=typed[:4096])
    inbound.store(item)
    return JsonResponse({"ok": True})


@require_GET
def simulator_inbox(request):
    _simulator_only()
    phone = _phone(request.GET.get("phone"))
    if phone is None:
        return JsonResponse({"messages": []})
    try:
        after = int(request.GET.get("after") or 0)
    except ValueError:
        after = 0
    since = datetime.fromtimestamp(after / 1_000_000, tz=UTC) if after else None
    time_filter = Q(created_at__gt=since) if since else Q()

    events = []
    for m in InboundMessage.objects.filter(time_filter, phone=phone).order_by("created_at")[:100]:
        if m.kind == "image" and m.media_id.startswith("sim:"):
            bubble = {"type": "image", "url": default_storage.url(m.media_id[4:]), "caption": m.text}
        elif m.kind == "location":
            bubble = {"type": "text", "text": f"📍 {m.latitude}, {m.longitude}"}
        else:
            bubble = {"type": "text", "text": m.text or m.reply_id}
        events.append((m.created_at, "in", bubble))
    for m in OutboundMessage.objects.filter(time_filter, phone=phone).order_by("created_at")[:100]:
        events.append((m.created_at, "out", m.payload))
    events.sort(key=lambda e: e[0])
    return JsonResponse(
        {
            "messages": [
                {
                    "id": _cursor(at),
                    "dir": direction,
                    "payload": payload,
                    "time": timezone.localtime(at).strftime("%H:%M"),
                }
                for at, direction, payload in events
            ]
        }
    )


@csrf_exempt
@require_POST
def simulator_reset(request):
    """Clear the chat for the given phones. Accounts, cases and orders are kept."""
    _simulator_only()
    phones = [p for p in (_phone(x) for x in request.POST.getlist("phone")) if p]
    Conversation.objects.filter(phone__in=phones).update(step="START", data={}, updated_at=timezone.now())
    InboundMessage.objects.filter(phone__in=phones).delete()
    OutboundMessage.objects.filter(phone__in=phones).delete()
    return JsonResponse({"ok": True})
