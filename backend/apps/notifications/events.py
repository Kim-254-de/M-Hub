"""Who gets an SMS when, called by the modules at the moment the event happens.

Each call queues at most one SMS per event (idempotent), sent after the transaction commits.
"""

from __future__ import annotations

from django.conf import settings

from apps.accounts.models import FarmerProfile
from apps.prescriptions.messages import sms_quantity

from .messages import REVIEW_ASSIGNED, ROUND_NAMES, farmer_message, to_gsm
from .models import SmsMessage
from .services import queue_sms


def _language(user) -> str:
    from apps.cases.services import farmer_language

    return farmer_language(user)


def _to_farmer(case, key: str, purpose: str, source_ref: str, **values):
    farmer = case.farmer
    if FarmerProfile.objects.filter(user=farmer, notifications_enabled=False).exists():
        return None  # the farmer turned SMS off in the app's settings
    return queue_sms(
        to=farmer.phone,
        body=farmer_message(key, _language(farmer), **values),
        purpose=purpose,
        source_ref=source_ref,
    )


def case_in_review(case, ai_diagnosis=None):
    """The case reached an agrovet: send the provisional AI result, or 'received' if the AI could not help."""
    from apps.diagnosis.review import provisional_result

    language = _language(case.farmer)
    provisional = provisional_result(case)
    if provisional and provisional["kind"] == "likely":
        disease = provisional["disease"]
        name = disease.display_name(language) if disease else provisional["name"]
        key, values = "ai_likely", {"disease": name, "percent": round(provisional["probability"] * 100)}
    elif provisional and provisional["kind"] == "healthy":
        key, values = "ai_healthy", {}
    else:
        key, values = "received", {}
    ref = f"ai:{ai_diagnosis.id}" if ai_diagnosis else f"case:{case.id}"
    return _to_farmer(case, key, SmsMessage.Purpose.AI_RESULT, ref, **values)


def retake_photos(case, reason: str, ai_diagnosis):
    return _to_farmer(case, f"retake_{reason}", SmsMessage.Purpose.RETAKE_PHOTOS, f"ai:{ai_diagnosis.id}")


def review_assigned(review):
    agrovet = review.agrovet
    body = REVIEW_ASSIGNED.format(
        ward=review.case.ward or "your area",
        round=ROUND_NAMES.get(review.round, "review"),
        hours=settings.DIAGNOSE["REVIEW_TIMEOUT_HOURS"],
    )
    return queue_sms(
        to=agrovet.phone or agrovet.user.phone,
        body=to_gsm(body),
        purpose=SmsMessage.Purpose.REVIEW_ASSIGNED,
        source_ref=f"review:{review.id}",
    )


def diagnosis_confirmed(final, *, ai_corrected: bool | None):
    case = final.case
    language = _language(case.farmer)
    return _to_farmer(
        case,
        "confirmed_corrected" if ai_corrected else "confirmed",
        SmsMessage.Purpose.DIAGNOSIS_CONFIRMED,
        f"case:{case.id}",
        agrovet=final.confirmed_by.name,
        disease=final.disease.display_name(language),
    )


def diagnosis_unknown(case):
    return _to_farmer(case, "unknown", SmsMessage.Purpose.DIAGNOSIS_UNKNOWN, f"case:{case.id}")


def prescription_issued(prescription):
    return _to_farmer(
        prescription.case,
        "prescription",
        SmsMessage.Purpose.PRESCRIPTION_ISSUED,
        f"prescription:{prescription.id}",
        code=prescription.code,
        product=prescription.approved_product.name,
        quantity=sms_quantity(prescription, _language(prescription.case.farmer)),
        expires=prescription.expires_at.astimezone(_nairobi()).strftime("%d/%m/%Y"),
    )


def _nairobi():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Africa/Nairobi")
