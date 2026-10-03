"""Africa's Talking SMS client.

Docs: https://developers.africastalking.com/docs/sms/sending/bulk
Sandbox: username "sandbox", host api.sandbox.africastalking.com; messages appear in the
simulator at https://simulator.africastalking.com instead of on real phones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Recipient statusCode values in the send response.
ACCEPTED_CODES = {100, 101, 102}  # Processed, Sent, Queued
TEMPORARY_CODES = {
    405,
    500,
    501,
    502,
}  # InsufficientBalance, InternalServerError, GatewayError, RejectedByGateway


class SmsError(Exception):
    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SmsConfigError(SmsError):
    """Missing or rejected credentials, or an unapproved sender ID."""


class SmsTemporaryError(SmsError):
    """Timeouts, 5xx, gateway errors, insufficient balance. Safe to retry later."""

    retryable = True


class SmsRejectedError(SmsError):
    """The number cannot receive this message (invalid, blacklisted, DND, unroutable)."""


@dataclass(frozen=True)
class SendResult:
    message_id: str
    status_code: int
    status: str
    cost: str


class AfricasTalkingClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        api_key: str,
        sender_id: str = "",
        timeout: tuple[float, float] = (5.0, 30.0),
        session: requests.Session | None = None,
    ):
        missing = [name for name, value in (("AT_USERNAME", username), ("AT_API_KEY", api_key)) if not value]
        if missing:
            raise SmsConfigError(f"SMS is not configured: {', '.join(missing)}")
        self._url = base_url.rstrip("/") + "/version1/messaging"
        self._username = username
        self._api_key = api_key
        self._sender_id = sender_id
        self._timeout = timeout
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls) -> AfricasTalkingClient:
        config = settings.SMS
        return cls(
            base_url=config["AT_BASE_URL"],
            username=config["AT_USERNAME"],
            api_key=config["AT_API_KEY"],
            sender_id=config["AT_SENDER_ID"],
            timeout=config["TIMEOUT"],
        )

    def send(self, *, to: str, message: str) -> SendResult:
        """Send one SMS to one number (+2547XXXXXXXX)."""
        data = {"username": self._username, "to": to, "message": message}
        if self._sender_id:
            data["from"] = self._sender_id
        try:
            response = self._session.post(
                self._url,
                data=data,
                headers={"apiKey": self._api_key, "Accept": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SmsTemporaryError(f"SMS request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise SmsConfigError(
                f"SMS credentials rejected (HTTP {response.status_code}): {response.text[:200]}",
                status_code=response.status_code,
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise SmsTemporaryError(f"SMS HTTP {response.status_code}", status_code=response.status_code)
        if not 200 <= response.status_code < 300:
            raise SmsRejectedError(
                f"SMS HTTP {response.status_code}: {response.text[:200]}", status_code=response.status_code
            )

        try:
            recipient = response.json()["SMSMessageData"]["Recipients"][0]
            status_code = int(recipient["statusCode"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            # e.g. {"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}
            detail = response.text[:200]
            if "sender" in detail.lower():
                raise SmsConfigError(f"SMS sender ID rejected: {detail}") from exc
            raise SmsRejectedError(f"Unexpected SMS response: {detail}") from exc

        status = str(recipient.get("status", ""))
        if status_code in ACCEPTED_CODES:
            return SendResult(
                message_id=str(recipient.get("messageId", "")),
                status_code=status_code,
                status=status,
                cost=str(recipient.get("cost", "")),
            )
        message = f"SMS not sent: {status_code} {status}"
        if status_code == 402:  # InvalidSenderId
            raise SmsConfigError(message, status_code=status_code)
        if status_code in TEMPORARY_CODES:
            raise SmsTemporaryError(message, status_code=status_code)
        raise SmsRejectedError(message, status_code=status_code)
