import hashlib
import hmac
import json
from unittest import mock

import pytest
import responses

from apps.whatsapp.models import InboundMessage, OutboundMessage
from apps.whatsapp.tasks import send_outbound_task
from apps.whatsapp.transport import queue, text_payload

pytestmark = pytest.mark.django_db

URL = "/whatsapp/webhook/"


@pytest.fixture(autouse=True)
def cloud(settings):
    settings.WHATSAPP = {**settings.WHATSAPP, "TRANSPORT": "cloud"}


def payload(msg: dict, sender="254712345678"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"wa_id": sender, "profile": {"name": "Peter Kamau"}}],
                            "messages": [{"from": sender, "timestamp": "1700000000", **msg}],
                        }
                    }
                ]
            }
        ],
    }


def post(client, body: dict, secret="test-wa-secret", capture=None):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(URL, data=raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)


def test_verification_handshake(client):
    ok = client.get(
        URL, {"hub.mode": "subscribe", "hub.verify_token": "test-wa-verify", "hub.challenge": "42"}
    )
    assert ok.status_code == 200 and ok.content == b"42"
    bad = client.get(URL, {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_bad_signature_rejected(client):
    raw = json.dumps(payload({"id": "wamid.1", "type": "text", "text": {"body": "hi"}})).encode()
    response = client.post(
        URL, data=raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=bad"
    )
    assert response.status_code == 403
    assert not InboundMessage.objects.exists()


def test_missing_app_secret_fails_closed(client, settings):
    settings.WHATSAPP = {**settings.WHATSAPP, "APP_SECRET": ""}
    response = post(client, payload({"id": "wamid.1", "type": "text", "text": {"body": "hi"}}), secret="")
    assert response.status_code == 403


def test_message_stored_once_and_handled(client, django_capture_on_commit_callbacks):
    body = payload({"id": "wamid.1", "type": "text", "text": {"body": "Hi"}})
    with (
        mock.patch("apps.whatsapp.tasks.send_outbound_task.delay"),
        mock.patch("apps.whatsapp.transport.CloudClient.mark_read"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            assert post(client, body).status_code == 200
        with django_capture_on_commit_callbacks(execute=True):
            assert post(client, body).status_code == 200  # Meta retry

    message = InboundMessage.objects.get()
    assert message.phone == "+254712345678" and message.status == InboundMessage.Status.DONE
    welcome = OutboundMessage.objects.get(phone="+254712345678")
    assert "AgriSense" in welcome.payload["interactive"]["body"]["text"]


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        (
            {
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "REG_START", "title": "Register"},
                },
            },
            {"kind": "reply", "reply_id": "REG_START"},
        ),
        (
            {
                "type": "interactive",
                "interactive": {"type": "list_reply", "list_reply": {"id": "COUNTY:Meru", "title": "Meru"}},
            },
            {"kind": "reply", "reply_id": "COUNTY:Meru"},
        ),
        (
            {"type": "image", "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "leaf"}},
            {"kind": "image", "media_id": "MEDIA1"},
        ),
        ({"type": "location", "location": {"latitude": -0.333, "longitude": 37.65}}, {"kind": "location"}),
        ({"type": "sticker", "sticker": {"id": "S1"}}, {"kind": "other"}),
    ],
)
def test_message_kinds_are_parsed(client, msg, expected):
    with mock.patch("apps.whatsapp.inbound.transaction.on_commit"):
        post(client, payload({"id": "wamid.k", **msg}))
    message = InboundMessage.objects.get()
    for field, value in expected.items():
        assert getattr(message, field) == value


def test_status_updates_and_foreign_numbers_ignored(client):
    status_only = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.x", "status": "delivered"}]}}]}],
    }
    with mock.patch("apps.whatsapp.inbound.transaction.on_commit"):
        post(client, status_only)
        post(
            client, payload({"id": "wamid.f", "type": "text", "text": {"body": "hi"}}, sender="447700900123")
        )
    assert not InboundMessage.objects.exists()


def test_webhook_off_when_using_simulator(client, settings):
    settings.WHATSAPP = {**settings.WHATSAPP, "TRANSPORT": "web"}
    assert client.get(URL).status_code == 404


@responses.activate
def test_outbound_sent_through_cloud_api(django_capture_on_commit_callbacks):
    responses.post(
        "https://graph.facebook.com/v23.0/1234567890/messages", json={"messages": [{"id": "wamid.out1"}]}
    )
    with django_capture_on_commit_callbacks(execute=True):
        message = queue("+254712345678", text_payload("Hello"))
    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SENT and message.provider_message_id == "wamid.out1"
    sent = json.loads(responses.calls[0].request.body)
    assert sent["to"] == "254712345678" and sent["text"]["body"] == "Hello"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-wa-token"


@responses.activate
def test_expired_token_fails_without_retry(django_capture_on_commit_callbacks):
    responses.post("https://graph.facebook.com/v23.0/1234567890/messages", status=401, json={"error": {}})
    with django_capture_on_commit_callbacks(execute=True):
        message = queue("+254712345678", text_payload("Hello"))
    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.FAILED


def test_notification_sent_once_per_event():
    first = queue("+254712345678", text_payload("Paid"), source_ref="order_paid:1")
    second = queue("+254712345678", text_payload("Paid"), source_ref="order_paid:1")
    assert first is not None and second is None
    assert send_outbound_task  # imported for the eager task registry
