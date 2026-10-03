"""Sending WhatsApp messages and fetching media.

Messages are queued as OutboundMessage rows inside the caller's transaction and
sent after commit by a Celery task, so a rolled-back action never messages anyone.
Two transports:
  cloud — Meta WhatsApp Cloud API (graph.facebook.com)
  web   — the development simulator page reads the queued rows instead
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction

from .models import OutboundMessage

logger = logging.getLogger(__name__)

# WhatsApp interactive message limits.
MAX_BUTTONS = 3
BUTTON_TITLE = 20
LIST_ROWS = 10
ROW_TITLE = 24
ROW_DESCRIPTION = 72
BODY = 1024
TEXT_BODY = 4096
HEADER = 60


class WhatsAppError(Exception):
    retryable = False


class WhatsAppTemporaryError(WhatsAppError):
    retryable = True


class WhatsAppConfigError(WhatsAppError):
    pass


def clip(text, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def wa_id(phone: str) -> str:
    """Cloud API recipients are digits only: +254712345678 -> 254712345678."""
    return phone.lstrip("+")


# --- Payload builders ----------------------------------------------------------


def text_payload(body: str) -> dict:
    return {"type": "text", "text": {"body": clip(body, TEXT_BODY), "preview_url": False}}


def buttons_payload(body: str, buttons: list[tuple[str, str]], header: str = "") -> dict:
    interactive = {
        "type": "button",
        "body": {"text": clip(body, BODY)},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": bid, "title": clip(title, BUTTON_TITLE)}}
                for bid, title in buttons[:MAX_BUTTONS]
            ]
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": clip(header, HEADER)}
    return {"type": "interactive", "interactive": interactive}


def list_payload(body: str, button: str, rows: list[tuple[str, str, str]], header: str = "") -> dict:
    """rows: (id, title, description). WhatsApp shows at most 10 rows."""
    interactive = {
        "type": "list",
        "body": {"text": clip(body, TEXT_BODY)},
        "action": {
            "button": clip(button, BUTTON_TITLE),
            "sections": [
                {
                    "title": clip(header or "Options", ROW_TITLE),
                    "rows": [
                        {
                            "id": rid,
                            "title": clip(title, ROW_TITLE),
                            "description": clip(desc, ROW_DESCRIPTION),
                        }
                        if desc
                        else {"id": rid, "title": clip(title, ROW_TITLE)}
                        for rid, title, desc in rows[:LIST_ROWS]
                    ],
                }
            ],
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": clip(header, HEADER)}
    return {"type": "interactive", "interactive": interactive}


def location_request_payload(body: str) -> dict:
    return {
        "type": "interactive",
        "interactive": {
            "type": "location_request_message",
            "body": {"text": clip(body, BODY)},
            "action": {"name": "send_location"},
        },
    }


# --- Queueing ----------------------------------------------------------------------


def queue(phone: str, payload: dict, *, source_ref: str = "") -> OutboundMessage | None:
    """Queue one message; with ``source_ref`` it is sent at most once. Sent after the transaction commits."""
    from .tasks import send_outbound_task

    try:
        with transaction.atomic():
            message = OutboundMessage.objects.create(phone=phone, payload=payload, source_ref=source_ref)
    except IntegrityError:
        logger.info("WhatsApp message %s to %s already queued", source_ref, phone)
        return None
    if settings.WHATSAPP["TRANSPORT"] == "cloud":
        transaction.on_commit(lambda: send_outbound_task.delay(str(message.id)))
    else:
        # The simulator page polls queued rows directly.
        OutboundMessage.objects.filter(pk=message.pk).update(status=OutboundMessage.Status.SENT)
    return message


def send_text(phone, body, **kw):
    return queue(phone, text_payload(body), **kw)


def send_buttons(phone, body, buttons, header="", **kw):
    return queue(phone, buttons_payload(body, buttons, header), **kw)


def send_list(phone, body, button, rows, header="", **kw):
    return queue(phone, list_payload(body, button, rows, header), **kw)


# --- Cloud API -----------------------------------------------------------------------


class CloudClient:
    def __init__(self, *, access_token: str, phone_number_id: str, api_version: str, timeout, session=None):
        if not access_token or not phone_number_id:
            raise WhatsAppConfigError("WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be set")
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._base = f"https://graph.facebook.com/{api_version}"
        self._timeout = timeout
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls) -> CloudClient:
        c = settings.WHATSAPP
        return cls(
            access_token=c["ACCESS_TOKEN"],
            phone_number_id=c["PHONE_NUMBER_ID"],
            api_version=c["API_VERSION"],
            timeout=c["TIMEOUT"],
        )

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def send(self, phone: str, payload: dict) -> str:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id(phone),
            **payload,
        }
        data = self._request("post", f"{self._base}/{self._phone_number_id}/messages", json=body)
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WhatsAppTemporaryError(f"Unexpected send response: {data}") from exc

    def mark_read(self, wamid: str) -> None:
        body = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wamid,
            "typing_indicator": {"type": "text"},
        }
        self._request("post", f"{self._base}/{self._phone_number_id}/messages", json=body)

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        info = self._request("get", f"{self._base}/{media_id}")
        try:
            response = self._session.get(info["url"], headers=self._headers(), timeout=self._timeout)
        except (KeyError, TypeError) as exc:
            raise WhatsAppTemporaryError(f"Media lookup returned no URL: {info}") from exc
        except requests.RequestException as exc:
            raise WhatsAppTemporaryError(f"Media download failed: {exc}") from exc
        if response.status_code != 200:
            raise WhatsAppTemporaryError(f"Media download HTTP {response.status_code}")
        return response.content, info.get("mime_type", "image/jpeg")

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = self._session.request(
                method, url, headers=self._headers(), timeout=self._timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise WhatsAppTemporaryError(f"WhatsApp request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if 200 <= response.status_code < 300:
            return data
        message = f"WhatsApp HTTP {response.status_code}: {str(data)[:300]}"
        if response.status_code in (401, 403):
            raise WhatsAppConfigError(message)
        if response.status_code == 429 or response.status_code >= 500:
            raise WhatsAppTemporaryError(message)
        raise WhatsAppError(message)


def download_media(media_id: str) -> tuple[bytes, str]:
    """Bytes and MIME type of an incoming image (Cloud API media id, or simulator upload path)."""
    if media_id.startswith("sim:"):
        name = media_id.split(":", 1)[1]
        if not name.startswith("whatsapp/sim/") or ".." in name:
            raise WhatsAppError("Invalid simulator media id")
        with default_storage.open(name, "rb") as fh:
            return fh.read(), "image/jpeg"
    return CloudClient.from_settings().download_media(media_id)


def mark_read(wamid: str) -> None:
    """Blue ticks and a typing indicator while the reply is prepared. Best effort."""
    if settings.WHATSAPP["TRANSPORT"] != "cloud":
        return
    try:
        CloudClient.from_settings().mark_read(wamid)
    except WhatsAppError as exc:
        logger.info("Could not mark %s read: %s", wamid, exc)
