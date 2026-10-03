"""Endpoints added for the farmer app: sign-up code, profile, voice note, outbreak alerts, adviser."""

import pytest
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import otp
from apps.accounts.models import Farm, FarmerProfile, User
from apps.advisory.models import AdviceExchange
from apps.advisory.providers import Reply
from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.diagnosis.models import AIDiagnosis, AISuggestion, FinalDiagnosis
from apps.notifications.models import SmsMessage
from apps.products.models import Disease
from apps.rewards.models import RewardEntry

pytestmark = pytest.mark.django_db

LAT, LNG = "-0.333000", "37.650000"


def client_for(user=None):
    api = APIClient()
    if user is not None:
        api.force_authenticate(user)
    return api


@pytest.fixture
def farmer(db):
    user = User.objects.create_user(username="f1", password="x", phone="+254700000001", first_name="Wanjiru")
    FarmerProfile.objects.create(user=user, ward="Chuka", county="Tharaka Nithi", consent_at=timezone.now())
    Farm.objects.create(farmer=user, latitude=LAT, longitude=LNG, size_acres="0.5")
    return user


@pytest.fixture
def agrovet(db):
    user = User.objects.create_user(username="agro", password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user, name="Mwangi Agrovet", pcpb_licence_no="L1", latitude=LAT, longitude=LNG, status="verified"
    )


@pytest.fixture
def late_blight(db):
    return Disease.objects.create(name="Late blight", local_names={"sw": "Baa chelewa"})


def confirm(farmer, agrovet, disease, *, lat=LAT, lng=LNG, ward="Chuka"):
    case = Case.objects.create(
        farmer=farmer, status=Case.Status.DIAGNOSED, ward=ward, latitude=lat, longitude=lng
    )
    FinalDiagnosis.objects.create(
        case=case,
        disease=disease,
        confidence="high",
        confirmed_by=agrovet,
        ward=ward,
        latitude=lat,
        longitude=lng,
    )
    return case


# --- Sign-up code -------------------------------------------------------------------------------


@pytest.fixture
def sms_on(settings):
    settings.SMS = {**settings.SMS, "ENABLED": True}
    settings.ACCOUNTS = {**settings.ACCOUNTS, "REQUIRE_OTP": True}


REGISTRATION = {"phone": "0712345678", "pin": "4821", "name": "Wanjiru", "language": "sw", "consent": True}


def test_sign_up_needs_the_sms_code(sms_on, monkeypatch):
    monkeypatch.setattr("apps.notifications.tasks.send_sms_task.delay", lambda message_id: None)
    monkeypatch.setattr(otp.secrets, "randbelow", lambda n: 123456)
    api = client_for()

    assert api.post(reverse("v1:auth-otp"), {"phone": "0712345678"}, format="json").status_code == 202
    message = SmsMessage.objects.get(purpose=SmsMessage.Purpose.SIGNUP_CODE)
    assert message.to == "+254712345678" and "Nambari yako ni 123456." in message.body

    # Without a verified phone the account is not created.
    assert api.post(reverse("v1:auth-register"), REGISTRATION, format="json").status_code == 400

    wrong = api.post(reverse("v1:auth-otp-verify"), {"phone": "0712345678", "code": "000000"}, format="json")
    assert wrong.status_code == 400 and wrong.data["code"] == "otp_wrong"
    verified = api.post(
        reverse("v1:auth-otp-verify"), {"phone": "0712345678", "code": "123456"}, format="json"
    )
    assert verified.status_code == 200

    response = api.post(
        reverse("v1:auth-register"),
        {**REGISTRATION, "phone_token": verified.data["phone_token"]},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert User.objects.get(phone="+254712345678").farmer_profile.ward == ""  # ward is optional now


def _token_for(phone):
    return signing.dumps({"phone": phone}, salt=otp.SIGNING_SALT)


def test_code_for_another_phone_does_not_register(sms_on):
    assert otp.phone_from_token("not-a-token") is None
    response = client_for().post(
        reverse("v1:auth-register"),
        {**REGISTRATION, "phone": "0722000000", "phone_token": _token_for("+254712345678")},
        format="json",
    )
    assert response.status_code == 400 and "phone_token" in response.data


def test_too_many_wrong_codes_lock_the_code(sms_on, settings, monkeypatch):
    settings.ACCOUNTS = {**settings.ACCOUNTS, "OTP_MAX_ATTEMPTS": 2}
    monkeypatch.setattr(otp.secrets, "randbelow", lambda n: 123456)
    otp.send_code("+254712345678")
    for _ in range(2):
        with pytest.raises(otp.OtpError, match="not correct"):
            otp.verify_code("+254712345678", "999999")
    with pytest.raises(otp.OtpError) as caught:
        otp.verify_code("+254712345678", "123456")  # even the right code: locked
    assert caught.value.code == "otp_locked"


# --- Profile ------------------------------------------------------------------------------------


def test_profile_read_and_update(farmer, settings):
    settings.ACCOUNTS = {**settings.ACCOUNTS, "SUPPORT_WHATSAPP": "+254700111222"}
    RewardEntry.objects.create(farmer=farmer, reason=RewardEntry.Reason.FOLLOW_UP, points=5, source_ref="x")
    api = client_for(farmer)

    me = api.get(reverse("v1:me")).data
    assert (me["name"], me["phone"], me["language"], me["points"]) == ("Wanjiru", "+254700000001", "sw", 5)
    assert me["support_whatsapp"] == "+254700111222" and len(me["farms"]) == 1

    updated = api.patch(reverse("v1:me"), {"language": "ki", "notifications_enabled": False}, format="json")
    assert updated.status_code == 200
    profile = FarmerProfile.objects.get(user=farmer)
    assert (profile.language, profile.notifications_enabled) == ("ki", False)


def test_notifications_off_means_no_case_sms(farmer, agrovet, late_blight, settings):
    from apps.notifications import events

    settings.SMS = {**settings.SMS, "ENABLED": True}
    FarmerProfile.objects.filter(user=farmer).update(notifications_enabled=False)
    case = confirm(farmer, agrovet, late_blight)
    assert events.diagnosis_unknown(case) is None


# --- Voice note ---------------------------------------------------------------------------------


def test_voice_note_upload(farmer):
    case = Case.objects.create(farmer=farmer, status=Case.Status.DRAFT)
    url = reverse("v1:case-voice-note", kwargs={"pk": case.pk})
    api = client_for(farmer)

    audio = SimpleUploadedFile("note.m4a", b"\x00" * 1000, content_type="audio/mp4")
    response = api.post(url, {"audio": audio}, format="multipart")
    assert response.status_code == 200 and response.data["voice_note"]

    text = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
    assert api.post(url, {"audio": text}, format="multipart").status_code == 400


# --- Outbreaks and similar cases ----------------------------------------------------------------------


def test_outbreak_alert_needs_enough_confirmed_cases_nearby(farmer, agrovet, late_blight):
    others = [User.objects.create_user(username=f"o{i}", password="x") for i in range(3)]
    api = client_for(farmer)
    url = reverse("v1:outbreak-alerts")

    confirm(others[0], agrovet, late_blight)
    confirm(others[1], agrovet, late_blight)
    confirm(others[2], agrovet, late_blight, lat="0.900000", lng="38.500000")  # far away
    assert api.get(url).data == []

    confirm(others[2], agrovet, late_blight, lat="-0.340000", lng="37.655000")
    [alert] = api.get(url).data
    assert alert["count"] == 3 and alert["name"] == "Baa chelewa"
    assert (
        alert["message"]
        == "Baa chelewa imethibitishwa na wakulima 3 karibu na Chuka wiki hii. Kagua zao lako."
    )


def test_diagnosis_shows_similar_cases_nearby(farmer, agrovet, late_blight):
    case = confirm(farmer, agrovet, late_blight)
    other = User.objects.create_user(username="o", password="x")
    confirm(other, agrovet, late_blight)

    ai = AIDiagnosis.objects.create(
        case=case, provider="kindwise", status=AIDiagnosis.Status.COMPLETED, is_plant=True, is_tomato=True
    )
    AISuggestion.objects.create(
        ai_diagnosis=ai, rank=1, external_id="x", name="Late blight", probability="0.8700"
    )

    data = client_for(farmer).get(reverse("v1:case-diagnosis", kwargs={"case_id": case.id})).data
    assert data["similar_nearby"] == 1 and data["disease_name"] == "Baa chelewa"
    assert data["ai_evidence"] == {"name": "Baa chelewa", "percent": 87}
    listed = client_for(farmer).get(reverse("v1:case-list")).data
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert rows[0]["disease"] == "Baa chelewa"


# --- Adviser ------------------------------------------------------------------------------------


class FakeProvider:
    def __init__(self, text):
        self.text = text

    def reply(self, *, system, user, model, allow_fallback=True):
        return Reply(
            text=self.text, model="gemini-3.8-flash", stop_reason="end_turn", usage={"input_tokens": 1}
        )


def test_ask_the_adviser_logs_the_exchange(farmer, agrovet, late_blight, monkeypatch):
    case = confirm(farmer, agrovet, late_blight)
    monkeypatch.setattr("apps.advisory.services.get_provider", lambda: FakeProvider("Tumia Ridomil 50 g."))
    url = reverse("v1:case-advice", kwargs={"case_id": case.id})

    response = client_for(farmer).post(url, {"question": "Nitumie dawa gani?"}, format="json")
    assert response.status_code == 200
    assert response.data["blocked"] is True and "Ridomil" not in response.data["answer"]
    exchange = AdviceExchange.objects.get(case=case)
    assert exchange.blocked and exchange.raw_answer == "Tumia Ridomil 50 g." and exchange.language == "sw"

    stranger = User.objects.create_user(username="s", password="x")
    FarmerProfile.objects.create(user=stranger, consent_at=timezone.now())
    assert client_for(stranger).post(url, {"question": "?"}, format="json").status_code == 404
