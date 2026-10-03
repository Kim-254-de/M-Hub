"""Safaricom Daraja client: OAuth, M-Pesa Express (STK push) and STK query.

Docs: https://developer.safaricom.co.ke/apis/MpesaExpressSimulate
      https://developer.safaricom.co.ke/apis/MpesaExpressQuery
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

NAIROBI = ZoneInfo("Africa/Nairobi")
ACCOUNT_REFERENCE_MAX = 12
TRANSACTION_DESC_MAX = 13


class MpesaError(Exception):
    retryable = False

    def __init__(self, message: str, *, error_code: str = "", status_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class MpesaConfigError(MpesaError):
    pass


class MpesaTemporaryError(MpesaError):
    """Timeouts, Safaricom busy/spike arrest, 5xx. Safe to retry later."""

    retryable = True


class MpesaRequestError(MpesaError):
    """Daraja rejected the request (bad phone, wrong credentials, invalid field)."""


@dataclass(frozen=True)
class StkPushResponse:
    merchant_request_id: str
    checkout_request_id: str
    customer_message: str


@dataclass(frozen=True)
class StkQueryResult:
    """``pending`` is True while M-Pesa is still waiting for the customer."""

    pending: bool
    result_code: str = ""
    result_desc: str = ""


def normalize_phone(phone: str) -> str:
    """Return a Safaricom-format number 2547XXXXXXXX / 2541XXXXXXXX, or raise ValueError."""
    digits = re.sub(r"[\s\-()]", "", phone or "").lstrip("+")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    if not re.fullmatch(r"254[71]\d{8}", digits):
        raise ValueError("Enter a valid Kenyan mobile number, e.g. 0712345678.")
    return digits


class MpesaClient:
    def __init__(
        self,
        *,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str,
        passkey: str,
        transaction_type: str,
        party_b: str,
        timeout: tuple[float, float],
        session: requests.Session | None = None,
    ):
        missing = [
            name
            for name, value in (
                ("MPESA_CONSUMER_KEY", consumer_key),
                ("MPESA_CONSUMER_SECRET", consumer_secret),
                ("MPESA_SHORTCODE", shortcode),
                ("MPESA_PASSKEY", passkey),
            )
            if not value
        ]
        if missing:
            raise MpesaConfigError(f"M-Pesa is not configured: {', '.join(missing)}")
        self._base_url = base_url.rstrip("/")
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._shortcode = str(shortcode)
        self._passkey = passkey
        self._transaction_type = transaction_type
        self._party_b = str(party_b or shortcode)
        self._timeout = timeout
        self._session = session or requests.Session()
        key_hash = hashlib.sha256(f"{self._base_url}:{consumer_key}".encode()).hexdigest()[:16]
        self._token_cache_key = f"mpesa:token:{key_hash}"

    @classmethod
    def from_settings(cls) -> MpesaClient:
        config = settings.MPESA
        return cls(
            base_url=config["BASE_URL"],
            consumer_key=config["CONSUMER_KEY"],
            consumer_secret=config["CONSUMER_SECRET"],
            shortcode=config["SHORTCODE"],
            passkey=config["PASSKEY"],
            transaction_type=config["TRANSACTION_TYPE"],
            party_b=config["PARTY_B"],
            timeout=config["TIMEOUT"],
        )

    # --- Public API ----------------------------------------------------------

    def stk_push(
        self, *, phone: str, amount: int, account_reference: str, description: str, callback_url: str
    ) -> StkPushResponse:
        if amount < 1:
            raise MpesaRequestError("Amount must be at least KES 1")
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": self._shortcode,
            "Password": self._password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": self._transaction_type,
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self._party_b,
            "PhoneNumber": phone,
            "CallBackURL": callback_url,
            "AccountReference": account_reference[:ACCOUNT_REFERENCE_MAX],
            "TransactionDesc": description[:TRANSACTION_DESC_MAX],
        }
        data = self._post("/mpesa/stkpush/v1/processrequest", body)
        if str(data.get("ResponseCode")) != "0" or not data.get("CheckoutRequestID"):
            raise MpesaRequestError(
                f"STK push not accepted: {data.get('ResponseDescription') or data}",
                error_code=str(data.get("ResponseCode", "")),
            )
        return StkPushResponse(
            merchant_request_id=str(data.get("MerchantRequestID", "")),
            checkout_request_id=str(data["CheckoutRequestID"]),
            customer_message=str(data.get("CustomerMessage", "")),
        )

    def stk_query(self, checkout_request_id: str) -> StkQueryResult:
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": self._shortcode,
            "Password": self._password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        try:
            data = self._post("/mpesa/stkpushquery/v1/query", body)
        except MpesaError as exc:
            # Daraja answers 500.001.1001 "The transaction is being processed" while the prompt is open.
            if "being processed" in str(exc).lower():
                return StkQueryResult(pending=True)
            raise
        if "ResultCode" not in data:
            return StkQueryResult(pending=True)
        return StkQueryResult(
            pending=False, result_code=str(data["ResultCode"]), result_desc=str(data.get("ResultDesc", ""))
        )

    # --- Internals -----------------------------------------------------------

    def _timestamp(self) -> str:
        return datetime.now(NAIROBI).strftime("%Y%m%d%H%M%S")

    def _password(self, timestamp: str) -> str:
        return base64.b64encode(f"{self._shortcode}{self._passkey}{timestamp}".encode()).decode()

    def _access_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            token = cache.get(self._token_cache_key)
            if token:
                return token
        try:
            response = self._session.get(
                f"{self._base_url}/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=(self._consumer_key, self._consumer_secret),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise MpesaTemporaryError(f"M-Pesa OAuth request failed: {exc}") from exc
        if response.status_code >= 500:
            raise MpesaTemporaryError(
                f"M-Pesa OAuth HTTP {response.status_code}", status_code=response.status_code
            )
        if response.status_code != 200:
            raise MpesaConfigError(
                f"M-Pesa OAuth rejected credentials (HTTP {response.status_code})",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
            token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3599))
        except (ValueError, KeyError, TypeError) as exc:
            raise MpesaTemporaryError("M-Pesa OAuth returned an unexpected body") from exc
        cache.set(self._token_cache_key, token, timeout=max(expires_in - 60, 60))
        return token

    def _post(self, path: str, body: dict, *, _retried: bool = False) -> dict:
        token = self._access_token(force_refresh=_retried)
        try:
            response = self._session.post(
                f"{self._base_url}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise MpesaTemporaryError(f"M-Pesa request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {}

        if 200 <= response.status_code < 300:
            return data

        error_code = str(data.get("errorCode", ""))
        detail = data.get("errorMessage") or response.text[:200]
        message = f"M-Pesa HTTP {response.status_code} {error_code}: {detail}"
        if error_code == "404.001.03" and not _retried:  # Invalid Access Token: refresh once
            cache.delete(self._token_cache_key)
            return self._post(path, body, _retried=True)
        if error_code.startswith("500.003") or response.status_code in (429, 502, 503, 504):
            raise MpesaTemporaryError(message, error_code=error_code, status_code=response.status_code)
        if "being processed" in message.lower() or "unable to lock subscriber" in message.lower():
            raise MpesaTemporaryError(message, error_code=error_code, status_code=response.status_code)
        raise MpesaRequestError(message, error_code=error_code, status_code=response.status_code)


def parse_stk_callback(payload: dict) -> dict:
    """Flatten a Daraja STK callback into a dict, or raise ValueError if malformed."""
    try:
        callback = payload["Body"]["stkCallback"]
        result = {
            "merchant_request_id": str(callback.get("MerchantRequestID", "")),
            "checkout_request_id": str(callback["CheckoutRequestID"]),
            "result_code": str(callback["ResultCode"]),
            "result_desc": str(callback.get("ResultDesc", "")),
        }
    except (KeyError, TypeError) as exc:
        raise ValueError("Not an STK callback payload") from exc
    items = (callback.get("CallbackMetadata") or {}).get("Item") or []
    metadata = {item.get("Name"): item.get("Value") for item in items if isinstance(item, dict)}
    result["amount"] = metadata.get("Amount")
    result["mpesa_receipt"] = metadata.get("MpesaReceiptNumber")
    result["phone"] = str(metadata["PhoneNumber"]) if metadata.get("PhoneNumber") else None
    return result
