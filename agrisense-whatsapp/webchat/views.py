import secrets
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import Agrovet, Farmer
from core.utils import normalize_phone
from payments.views import apply_result
from whatsapp.flow import Incoming, handle
from whatsapp.models import ChatSession

from .models import WebMessage

MAX_UPLOAD = 8 * 1024 * 1024


def _web_only():
    if settings.WA_TRANSPORT != "web":
        raise Http404("The browser chat runs only with WA_TRANSPORT=web")


def _phone(raw, default=""):
    return normalize_phone(raw) or default


@require_GET
def page(request):
    _web_only()
    agrovet = Agrovet.objects.filter(is_verified=True).order_by("id").first()
    farmer_phone = _phone(request.GET.get("farmer"), "254712345678")
    agrovet_phone = _phone(request.GET.get("agrovet"), agrovet.phone if agrovet else "")
    if agrovet and agrovet_phone != agrovet.phone:
        agrovet = Agrovet.objects.filter(phone=agrovet_phone).first()
    return render(request, "webchat/chat.html", {
        "farmer_phone": farmer_phone,
        "farmer_name": request.GET.get("name", "Peter Kamau"),
        "agrovet_phone": agrovet_phone,
        "agrovet_name": agrovet.name if agrovet else "",
        "single": request.GET.get("single") == "1",
    })


def _serialize(m):
    return {
        "id": m.pk,
        "dir": m.direction,
        "payload": m.payload,
        "time": timezone.localtime(m.created_at).strftime("%H:%M"),
    }


@require_GET
def inbox(request):
    _web_only()
    phone = _phone(request.GET.get("phone"))
    after = int(request.GET.get("after") or 0)
    msgs = WebMessage.objects.filter(phone=phone, id__gt=after)[:100] if phone else []
    return JsonResponse({"messages": [_serialize(m) for m in msgs]})


@csrf_exempt
@require_POST
def send(request):
    _web_only()
    phone = _phone(request.POST.get("phone"))
    if not phone:
        return JsonResponse({"error": "bad phone"}, status=400)
    msg = Incoming(phone=phone, wamid=f"web.{uuid.uuid4().hex}", name=request.POST.get("name", ""))
    bubble = {}
    image = request.FILES.get("image")
    if image:
        if image.size > MAX_UPLOAD or not (image.content_type or "").startswith("image/"):
            return JsonResponse({"error": "Please send an image under 8 MB."}, status=400)
        ext = Path(image.name).suffix.lower() if Path(image.name).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
        rel = default_storage.save(f"webchat/uploads/{phone}_{uuid.uuid4().hex[:10]}{ext}", image)
        msg.kind, msg.media_id, msg.mime = "image", f"web:{rel}", image.content_type
        msg.text = request.POST.get("text", "")
        bubble = {"type": "image", "url": f"/media/{rel}", "caption": msg.text}
    elif request.POST.get("reply_id"):
        msg.kind, msg.reply_id = "reply", request.POST["reply_id"]
        msg.text = request.POST.get("title", "")
        bubble = {"type": "reply", "text": msg.text}
    else:
        msg.text = request.POST.get("text", "").strip()
        if not msg.text:
            return JsonResponse({"error": "empty"}, status=400)
        bubble = {"type": "text", "text": msg.text}

    WebMessage.objects.create(phone=phone, direction=WebMessage.IN, payload=bubble)
    handle(msg)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def stk(request):
    """The farmer pressed OK (with PIN) or Cancel on the M-Pesa prompt."""
    _web_only()
    checkout_id = request.POST.get("checkout_id", "")
    ok = request.POST.get("action") == "ok"
    for m in WebMessage.objects.filter(direction=WebMessage.STK, payload__checkout_id=checkout_id):
        m.payload["resolved"] = True
        m.save(update_fields=["payload"])
    receipt = "T" + secrets.token_hex(5).upper()[:9] if ok else ""
    apply_result({"checkout_id": checkout_id, "ok": ok, "receipt": receipt,
                  "result_desc": "" if ok else "Request cancelled by user"})
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def reset(request):
    """Start the demo from zero for the given phones (deletes their farmer record and chat)."""
    _web_only()
    phones = [_phone(p) for p in request.POST.getlist("phone")]
    phones = [p for p in phones if p]
    Farmer.objects.filter(phone__in=phones).delete()
    ChatSession.objects.filter(phone__in=phones).delete()
    WebMessage.objects.filter(phone__in=phones).delete()
    return JsonResponse({"ok": True})
