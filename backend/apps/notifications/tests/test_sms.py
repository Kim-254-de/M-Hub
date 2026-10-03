"""SMS via Africa's Talking: client, outbox, delivery reports and templates."""

from urllib.parse import parse_qs

import pytest
import requests
import responses
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.notifications import services
from apps.notifications.integrations import africastalking as at
from apps.notifications.messages import FARMER_MESSAGES, REVIEW_ASSIGNED, farmer_message
from apps.notifications.models import SmsMessage

pytestmark = pytest.mark.django_db

SEND_URL = "https://at.test/version1/messaging"
REPORT_PATH = "/api/v1/notifications/sms/delivery/test-sms-token/"


def at_response(status_code=101, status="Success", message_id="ATXid_abc123"):
    return {
        "SMSMessageData": {
            "Message": "Sent to 1/1 Total Cost: KES 0.8000",
            "Recipients": [
                {
                    "statusCode": status_code,
                    "number": "+254712345678",
                    "status": status,
                    "cost": "KES 0.8000",
                    "messageId": message_id,
                }
            ],
        }
    }


@pytest.fixture(autouse=True)
def sms_enabled():
    with override_settings(SMS={**settings.SMS, "ENABLED": True}):
        yield


def client(**kwargs):
    return at.AfricasTalkingClient(base_url="https://at.test", username="sandbox", api_key="key", **kwargs)


# --- Client ------------------------------------------------------------------------


@responses.activate
def test_client_sends_form_with_api_key_and_parses_recipient():
    responses.post(SEND_URL, json=at_response())

    result = client(sender_id="AGRISENSE").send(to="+254712345678", message="Hello")

    assert result == at.SendResult(
        message_id="ATXid_abc123", status_code=101, status="Success", cost="KES 0.8000"
    )
    request = responses.calls[0].request
    assert request.headers["apiKey"] == "key"
    assert request.headers["Accept"] == "application/json"
    assert parse_qs(request.body) == {
        "username": ["sandbox"],
        "to": ["+254712345678"],
        "message": ["Hello"],
        "from": ["AGRISENSE"],
    }


@pytest.mark.parametrize(
    ("status_code", "error"),
    [
        (403, at.SmsRejectedError),  # InvalidPhoneNumber
        (406, at.SmsRejectedError),  # UserInBlacklist
        (402, at.SmsConfigError),  # InvalidSenderId
        (405, at.SmsTemporaryError),  # InsufficientBalance: retry after top-up
        (500, at.SmsTemporaryError),
        (501, at.SmsTemporaryError),
    ],
)
@responses.activate
def test_client_classifies_recipient_errors(status_code, error):
    responses.post(SEND_URL, json=at_response(status_code=status_code, status="Failed"))
    with pytest.raises(error):
        client().send(to="+254712345678", message="Hello")


@responses.activate
def test_client_http_errors():
    responses.post(SEND_URL, status=401, body="The supplied authentication is invalid")
    with pytest.raises(at.SmsConfigError):
        client().send(to="+254712345678", message="Hello")

    responses.replace(responses.POST, SEND_URL, status=503)
    with pytest.raises(at.SmsTemporaryError):
        client().send(to="+254712345678", message="Hello")

    responses.replace(responses.POST, SEND_URL, body=requests.ConnectTimeout("timed out"))
    with pytest.raises(at.SmsTemporaryError):
        client().send(to="+254712345678", message="Hello")


@responses.activate
def test_client_rejected_sender_id_without_recipients():
    responses.post(SEND_URL, json={"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}})
    with pytest.raises(at.SmsConfigError):
        client(sender_id="NOTMINE").send(to="+254712345678", message="Hello")


def test_client_requires_credentials():
    with pytest.raises(at.SmsConfigError):
        at.AfricasTalkingClient(base_url="https://at.test", username="sandbox", api_key="")


# --- Outbox -----------------------------------------------------------------------------


@responses.activate
def test_queued_sms_is_sent_after_commit(django_capture_on_commit_callbacks):
    responses.post(SEND_URL, json=at_response())

    with django_capture_on_commit_callbacks(execute=True):
        message = services.queue_sms(
            to="0712 345 678", body="Hello", purpose="ai_result", source_ref="case:1"
        )

    message.refresh_from_db()
    assert message.to == "+254712345678"
    assert (message.status, message.provider_message_id, message.attempts) == ("sent", "ATXid_abc123", 1)
    assert message.sent_at is not None


def test_same_event_is_queued_once():
    first = services.queue_sms(to="+254712345678", body="Hello", purpose="ai_result", source_ref="case:1")
    assert first is not None
    assert (
        services.queue_sms(to="+254712345678", body="Again", purpose="ai_result", source_ref="case:1") is None
    )
    assert SmsMessage.objects.count() == 1


def test_nothing_queued_when_disabled_or_number_invalid():
    assert services.queue_sms(to=None, body="x", purpose="ai_result", source_ref="a") is None
    assert services.queue_sms(to="12345", body="x", purpose="ai_result", source_ref="b") is None
    with override_settings(SMS={**settings.SMS, "ENABLED": False}):
        assert services.queue_sms(to="+254712345678", body="x", purpose="ai_result", source_ref="c") is None
    assert not SmsMessage.objects.exists()


@responses.activate
def test_temporary_failure_retries_until_max_attempts():
    responses.post(SEND_URL, status=503)
    message = SmsMessage.objects.create(to="+254712345678", body="x", purpose="ai_result", source_ref="r")

    assert services.send_sms(message.id) is services.SendOutcome.RETRY
    message.refresh_from_db()
    assert (message.status, message.attempts) == ("queued", 1)

    SmsMessage.objects.filter(pk=message.pk).update(attempts=settings.SMS["MAX_ATTEMPTS"] - 1)
    assert services.send_sms(message.id) is services.SendOutcome.FAILED
    message.refresh_from_db()
    assert message.status == "failed" and "503" in message.error


@responses.activate
def test_rejected_number_fails_without_retry_and_sent_messages_are_not_resent():
    responses.post(SEND_URL, json=at_response(status_code=403, status="InvalidPhoneNumber"))
    rejected = SmsMessage.objects.create(to="+254712345678", body="x", purpose="ai_result", source_ref="r1")
    assert services.send_sms(rejected.id) is services.SendOutcome.FAILED

    sent = SmsMessage.objects.create(
        to="+254712345678", body="x", purpose="ai_result", source_ref="r2", status="sent"
    )
    assert services.send_sms(sent.id) is services.SendOutcome.SKIPPED
    assert len(responses.calls) == 1


# --- Delivery reports ----------------------------------------------------------------------


def test_delivery_reports():
    message = SmsMessage.objects.create(
        to="+254712345678",
        body="x",
        purpose="ai_result",
        source_ref="d",
        status="sent",
        provider_message_id="ATXid_1",
    )
    api = APIClient()

    assert (
        api.post(
            "/api/v1/notifications/sms/delivery/wrong/", {"id": "ATXid_1", "status": "Success"}
        ).status_code
        == 404
    )
    assert api.post(REPORT_PATH, {"status": "Success"}).status_code == 400
    assert api.post(REPORT_PATH, {"id": "unknown", "status": "Success"}).status_code == 200

    assert (
        api.post(
            REPORT_PATH, {"id": "ATXid_1", "status": "Success", "phoneNumber": "+254712345678"}
        ).status_code
        == 200
    )
    message.refresh_from_db()
    assert message.status == "delivered" and message.delivered_at is not None

    # A late failure report never overrides a delivery.
    api.post(REPORT_PATH, {"id": "ATXid_1", "status": "Failed", "failureReason": "UserInBlacklist"})
    message.refresh_from_db()
    assert message.status == "delivered"


def test_failed_delivery_report_records_reason():
    message = SmsMessage.objects.create(
        to="+254712345678",
        body="x",
        purpose="ai_result",
        source_ref="f",
        status="sent",
        provider_message_id="ATXid_2",
    )
    APIClient().post(REPORT_PATH, {"id": "ATXid_2", "status": "Failed", "failureReason": "AbsentSubscriber"})
    message.refresh_from_db()
    assert (message.status, message.error) == ("failed", "AbsentSubscriber")


def test_delivery_report_url_matches_route():
    assert reverse("v1:sms-delivery-report", kwargs={"token": "test-sms-token"}) == REPORT_PATH


# --- Templates ------------------------------------------------------------------------------

# Characters that would force UCS-2 (70 per SMS) or count double in GSM-7.
NOT_PLAIN_GSM = set("`[]{}\\^~|")
VALUES = {
    "disease": "Late blight",
    "percent": 98,
    "agrovet": "Chuka Farmers Agrovet",
    "code": "AGR-7F3K9Q",
    "product": "Ridomil Gold MZ 68 WG",
    "quantity": "1 pack of 250 g (125 g needed)",
    "expires": "17/10/2026",
    "minutes": 10,
}


@pytest.mark.parametrize("key", sorted(FARMER_MESSAGES))
@pytest.mark.parametrize("language", ["en", "sw"])
def test_farmer_messages_are_plain_gsm_and_fit_one_sms(key, language):
    text = farmer_message(key, language, **VALUES)
    assert all(32 <= ord(c) < 127 for c in text) and not set(text) & NOT_PLAIN_GSM, text
    # The prescription carries product and dose, so it may take two parts; everything else fits one.
    assert len(text) <= (306 if key == "prescription" else 160), (len(text), text)


def test_agrovet_message_fits_one_sms():
    text = REVIEW_ASSIGNED.format(ward="Chuka Township", round="second opinion", hours=24)
    assert len(text) <= 160


def test_curly_quotes_from_product_names_are_made_plain():
    text = farmer_message("prescription", "en", **{**VALUES, "product": "Farmer’s “Best” – WP"})
    assert 'Farmer\'s "Best" - WP' in text
