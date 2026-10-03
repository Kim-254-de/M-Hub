"""Sign-up codes by SMS: proves the farmer holds the phone before an account is created."""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from apps.notifications.messages import farmer_message
from apps.notifications.models import SmsMessage
from apps.notifications.services import queue_sms

logger = logging.getLogger(__name__)

SIGNING_SALT = "accounts.phone-verified"


class OtpError(Exception):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def _key(phone: str) -> str:
    return f"otp:{phone}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def send_code(phone: str, language: str = "sw") -> None:
    """Text a fresh 6-digit code to ``phone``; any earlier code stops working."""
    config = settings.ACCOUNTS
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_key(phone), {"hash": _hash(code), "attempts": 0}, timeout=config["OTP_TTL_MINUTES"] * 60)
    message = queue_sms(
        to=phone,
        body=farmer_message("signup_code", language, code=code, minutes=config["OTP_TTL_MINUTES"]),
        purpose=SmsMessage.Purpose.SIGNUP_CODE,
        source_ref=f"signup:{phone}:{timezone.now().timestamp()}",
    )
    if message is None and settings.DEBUG:
        # SMS is off in local development: the code goes to the server log instead.
        logger.warning("Sign-up code for %s: %s", phone, code)


def verify_code(phone: str, code: str) -> str:
    """Check the code and return a token that proves ``phone`` was verified (used at sign-up)."""
    entry = cache.get(_key(phone))
    if entry is None:
        raise OtpError("The code has expired. Ask for a new one.", code="otp_expired")
    if entry["attempts"] >= settings.ACCOUNTS["OTP_MAX_ATTEMPTS"]:
        cache.delete(_key(phone))
        raise OtpError("Too many wrong codes. Ask for a new one.", code="otp_locked")
    if not secrets.compare_digest(entry["hash"], _hash(code.strip())):
        entry["attempts"] += 1
        cache.set(_key(phone), entry, timeout=settings.ACCOUNTS["OTP_TTL_MINUTES"] * 60)
        raise OtpError("That code is not correct.", code="otp_wrong")
    cache.delete(_key(phone))
    return signing.dumps({"phone": phone}, salt=SIGNING_SALT)


def phone_from_token(token: str) -> str | None:
    max_age = settings.ACCOUNTS["OTP_TTL_MINUTES"] * 60 * 3  # time to finish the sign-up form
    try:
        return signing.loads(token, salt=SIGNING_SALT, max_age=max_age)["phone"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
