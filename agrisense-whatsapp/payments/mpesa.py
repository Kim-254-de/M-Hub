"""M-Pesa Daraja STK push (Lipa na M-Pesa Online)."""
import base64
import logging
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)


def _base():
    return "https://api.safaricom.co.ke" if settings.MPESA_ENV == "production" else "https://sandbox.safaricom.co.ke"


def get_token():
    token = cache.get("mpesa_token")
    if token:
        return token
    r = requests.get(
        f"{_base()}/oauth/v1/generate?grant_type=client_credentials",
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]
    cache.set("mpesa_token", token, int(data.get("expires_in", 3599)) - 60)
    return token


def is_simulated():
    """Browser demo without Daraja keys: the chat page shows its own M-Pesa PIN prompt."""
    return settings.WA_TRANSPORT == "web" and not (settings.MPESA_CONSUMER_KEY and settings.MPESA_PASSKEY)


def callback_url():
    return f"{settings.PUBLIC_BASE_URL}/payments/mpesa/callback/{settings.MPESA_CALLBACK_TOKEN}/"


def stk_push(phone, amount, account_ref, description):
    """Returns (checkout_request_id, error_message)."""
    if is_simulated():
        import uuid
        return f"ws_CO_SIM{uuid.uuid4().hex[:14].upper()}", None
    if not (settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET and settings.MPESA_PASSKEY):
        return None, "M-Pesa is not configured on the server."
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()
    ).decode()
    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": settings.MPESA_TRANSACTION_TYPE,
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": callback_url(),
        "AccountReference": account_ref[:12],
        "TransactionDesc": description[:13],
    }
    try:
        r = requests.post(
            f"{_base()}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=30,
        )
        data = r.json()
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.error("STK push failed: %s", exc)
        return None, "Could not reach M-Pesa. Please try again."
    if data.get("ResponseCode") == "0":
        return data["CheckoutRequestID"], None
    log.error("STK push rejected: %s", data)
    return None, data.get("errorMessage") or data.get("ResponseDescription") or "M-Pesa rejected the request."


def parse_callback(body):
    """Return dict(checkout_id, ok, receipt, result_desc) from a Daraja callback body."""
    cb = (body.get("Body") or {}).get("stkCallback") or {}
    items = {i.get("Name"): i.get("Value") for i in (cb.get("CallbackMetadata") or {}).get("Item", [])}
    return {
        "checkout_id": cb.get("CheckoutRequestID", ""),
        "ok": cb.get("ResultCode") == 0,
        "receipt": str(items.get("MpesaReceiptNumber", "")),
        "result_desc": cb.get("ResultDesc", ""),
    }
