"""Thin wrapper around the WhatsApp Cloud API (graph.facebook.com).

Every send_* function returns the API JSON (or {} on failure) and never raises,
so one failed message can't crash a conversation.
"""
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)
TIMEOUT = 20


def _base():
    return f"https://graph.facebook.com/{settings.WA_API_VERSION}"


def _headers():
    return {"Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}"}


def _clip(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _post(payload):
    payload = {"messaging_product": "whatsapp", **payload}
    if settings.WA_TRANSPORT == "web":
        from webchat.outbox import deliver
        return deliver(payload)
    url = f"{_base()}/{settings.WA_PHONE_NUMBER_ID}/messages"
    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=TIMEOUT)
        if r.status_code >= 400:
            log.error("WhatsApp send failed %s: %s", r.status_code, r.text)
            return {}
        return r.json()
    except requests.RequestException as exc:
        log.error("WhatsApp send error: %s", exc)
        return {}


def send_text(to, body):
    return _post({"to": to, "type": "text", "text": {"body": _clip(body, 4096), "preview_url": False}})


def send_buttons(to, body, buttons, header=None, footer=None):
    """buttons: list of (id, title) — max 3, title max 20 chars."""
    interactive = {
        "type": "button",
        "body": {"text": _clip(body, 1024)},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": bid, "title": _clip(title, 20)}}
                for bid, title in buttons[:3]
            ]
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": _clip(header, 60)}
    if footer:
        interactive["footer"] = {"text": _clip(footer, 60)}
    return _post({"to": to, "type": "interactive", "interactive": interactive})


def send_list(to, body, button_label, sections, header=None, footer=None):
    """sections: list of (section_title, [(row_id, title, description), ...]).

    WhatsApp allows at most 10 rows in total; titles 24 chars, descriptions 72.
    """
    out, total = [], 0
    for title, rows in sections:
        clean = []
        for row in rows:
            if total >= 10:
                break
            rid, rtitle, *rest = row
            item = {"id": rid, "title": _clip(rtitle, 24)}
            if rest and rest[0]:
                item["description"] = _clip(rest[0], 72)
            clean.append(item)
            total += 1
        if clean:
            out.append({"title": _clip(title, 24), "rows": clean})
    interactive = {
        "type": "list",
        "body": {"text": _clip(body, 4096)},
        "action": {"button": _clip(button_label, 20), "sections": out},
    }
    if header:
        interactive["header"] = {"type": "text", "text": _clip(header, 60)}
    if footer:
        interactive["footer"] = {"text": _clip(footer, 60)}
    return _post({"to": to, "type": "interactive", "interactive": interactive})


def send_image(to, link, caption=""):
    return _post({"to": to, "type": "image", "image": {"link": link, "caption": _clip(caption, 1024)}})


def send_template(to, name, lang="en", body_params=None, button_payloads=None):
    """Send an approved template (needed outside the 24-hour reply window)."""
    components = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_params],
        })
    for i, payload in enumerate(button_payloads or []):
        components.append({
            "type": "button", "sub_type": "quick_reply", "index": str(i),
            "parameters": [{"type": "payload", "payload": payload}],
        })
    template = {"name": name, "language": {"code": lang}}
    if components:
        template["components"] = components
    return _post({"to": to, "type": "template", "template": template})


def mark_read(message_id):
    """Blue ticks + 'typing…' indicator while we work on the reply."""
    return _post({
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    })


def download_media(media_id):
    """Return (bytes, mime_type) for an incoming image, or (None, None)."""
    if media_id.startswith("web:"):
        from webchat.outbox import read_upload
        return read_upload(media_id)
    try:
        meta = requests.get(f"{_base()}/{media_id}", headers=_headers(), timeout=TIMEOUT)
        meta.raise_for_status()
        info = meta.json()
        file = requests.get(info["url"], headers=_headers(), timeout=60)
        file.raise_for_status()
        return file.content, info.get("mime_type", "image/jpeg")
    except (requests.RequestException, KeyError, ValueError) as exc:
        log.error("Media download failed for %s: %s", media_id, exc)
        return None, None
