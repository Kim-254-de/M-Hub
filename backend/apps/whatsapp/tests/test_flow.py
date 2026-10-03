from datetime import timedelta

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import FarmerProfile, User
from apps.cases.models import Case, CasePhoto
from apps.notifications import events
from apps.notifications.models import SmsMessage
from apps.purchases import services as purchases
from apps.purchases.models import Order, Payment, Verification
from apps.purchases.tests.conftest import CALLBACK_PATH, OCR_URL, mock_stk_push, ocr_response, stk_callback
from apps.rewards.services import balance
from apps.whatsapp.messages import MESSAGES
from apps.whatsapp.models import Conversation

from .conftest import PHONE, all_text, body_of, choose_location, ids_of, register, sharp_photo

pytestmark = pytest.mark.django_db


# --- registration ------------------------------------------------------------------


def test_registration_needs_only_the_phone_number_and_consent(chat):
    replies = register(chat)
    user = User.objects.get(phone=PHONE)
    profile = FarmerProfile.objects.get(user=user)
    assert user.role == User.Role.FARMER and not user.has_usable_password()
    assert user.first_name == ""
    assert (profile.language, profile.county, profile.ward) == ("en", "", "")
    assert profile.consent_at is not None
    assert "You're registered" in all_text(replies)
    assert "REPORT" in ids_of(replies[-1])  # main menu


def test_consent_screen_shows_the_number_and_explains_data_use(chat):
    chat(text="Hi")
    replies = chat(reply_id="REG_START")
    assert "0712 345 678" in body_of(replies[-1])
    assert "Data Protection Act" in body_of(replies[-1])
    assert not User.objects.filter(phone=PHONE).exists()  # nothing stored before consent


def test_declining_consent_stores_nothing(chat):
    chat(text="Hi")
    chat(reply_id="REG_START")
    replies = chat(reply_id="REG_DECLINE")
    assert "nothing has been saved" in all_text(replies)
    assert not User.objects.exists()


# --- farm location: Mt. Kenya region -> county -> sub-county -> ward ------------------


def test_first_upload_asks_location_drilling_down_to_the_ward(chat):
    register(chat)
    replies = chat(reply_id="REPORT")
    assert "Mt. Kenya region" in body_of(replies[-1])
    assert "LOC_C:Meru" in ids_of(replies[-1]) and len(ids_of(replies[-1])) == 9

    replies = chat(reply_id="LOC_C:Tharaka-Nithi")
    assert ids_of(replies[-1]) == ["LOC_S:Chuka/Igambang'ombe", "LOC_S:Maara", "LOC_S:Tharaka"]
    replies = chat(reply_id="LOC_S:Maara")
    assert "LOC_W:Chogoria" in ids_of(replies[-1])

    replies = chat(reply_id="LOC_W:Chogoria")
    profile = FarmerProfile.objects.get(user__phone=PHONE)
    assert (profile.county, profile.sub_county, profile.ward) == ("Tharaka-Nithi", "Maara", "Chogoria")
    assert "Chogoria, Maara, Tharaka-Nithi" in all_text(replies)
    assert Conversation.objects.get(phone=PHONE).step == "R_LOCATION"  # continues to the upload
    assert Case.objects.filter(farmer__phone=PHONE, status=Case.Status.DRAFT).exists()


def test_long_lists_are_paged(chat):
    register(chat)
    chat(reply_id="REPORT")
    replies = chat(reply_id="LOC_C:Kiambu")  # 12 sub-counties
    ids = ids_of(replies[-1])
    assert len(ids) == 10 and ids[-1] == "LOC_MORE:L_SUB_COUNTY:1"
    replies = chat(reply_id="LOC_MORE:L_SUB_COUNTY:1")
    ids = ids_of(replies[-1])
    assert ids == ["LOC_S:Limuru", "LOC_S:Ruiru", "LOC_S:Thika Town", "LOC_MORE:L_SUB_COUNTY:0"]


def test_choice_from_another_county_is_refused(chat):
    register(chat)
    chat(reply_id="REPORT")
    chat(reply_id="LOC_C:Meru")
    chat(reply_id="LOC_S:Maara")  # Maara is in Tharaka-Nithi
    assert FarmerProfile.objects.get(user__phone=PHONE).ward == ""
    assert Conversation.objects.get(phone=PHONE).step == "MENU"


def test_location_can_be_changed_from_the_menu(chat, farmer):
    chat(text="Hi")
    chat(reply_id="LOCATION")
    choose_location(chat, "Meru", "South Imenti", "Nkuene")
    profile = FarmerProfile.objects.get(user=farmer)
    assert (profile.county, profile.sub_county, profile.ward) == ("Meru", "South Imenti", "Nkuene")


def test_menu_offers_tomato_photo_upload(chat, farmer):
    replies = chat(text="Hi")
    rows = replies[-1]["interactive"]["action"]["sections"][0]["rows"]
    assert rows[0]["title"] == "📸 Upload tomato photo"
    assert "blight" in rows[0]["description"]


def test_existing_app_farmer_is_linked(chat, farmer):
    replies = chat(text="Hi")
    assert "linked to your AgriSense account" in all_text(replies)
    assert Conversation.objects.get(phone=PHONE).user == farmer


def test_agrovet_accounts_are_sent_to_the_app(chat, agrovet):
    agrovet.user.phone = PHONE
    agrovet.user.save()
    replies = chat(text="Hi")
    assert "agrovet tools are in the AgriSense app" in all_text(replies)


# --- report a problem (Detect) ----------------------------------------------------


def report(chat):
    chat(reply_id="REPORT")
    chat(latitude="-0.333000", longitude="37.650000")
    chat(image=sharp_photo())
    chat(image=sharp_photo())
    chat(image=sharp_photo())
    chat(reply_id="STARTED:3_to_7_days")
    chat(reply_id="SHARE:some")
    chat(reply_id="WEATHER:rainy")
    return chat(reply_id="SPRAYED:no")


def test_report_three_photos_questions_and_submit(chat, farmer, no_ai_run):
    replies = report(chat)
    case = Case.objects.get(farmer=farmer)
    assert case.status == Case.Status.REPORTED
    assert case.channel == Case.Channel.WHATSAPP
    assert sorted(case.photos.values_list("type", flat=True)) == sorted(CasePhoto.REQUIRED_TYPES)
    assert case.symptom_answers["started"] == "3_to_7_days"
    assert case.symptom_answers["recent_weather"] == ["rainy"]
    assert case.symptom_answers["already_sprayed"] is False
    assert str(case.latitude) == "-0.333000"
    assert "Report sent" in all_text(replies)


def test_blurry_photo_is_retaken(chat, farmer):
    import io

    from PIL import Image

    flat = io.BytesIO()
    Image.new("RGB", (900, 700), (120, 160, 90)).save(flat, format="JPEG")
    chat(reply_id="REPORT")
    chat(text="skip")
    replies = chat(image=flat.getvalue())
    assert "blurry" in all_text(replies).lower()
    assert not CasePhoto.objects.exists()


def test_sprayed_product_is_recorded(chat, farmer):
    chat(reply_id="REPORT")
    chat(text="skip")
    for _ in range(3):
        chat(image=sharp_photo())
    chat(reply_id="STARTED:less_than_3_days")
    chat(reply_id="SHARE:few")
    chat(reply_id="WEATHER:humid")
    chat(reply_id="SPRAYED:yes")
    chat(text="Copper oxychloride")
    case = Case.objects.get(farmer=farmer)
    assert case.symptom_answers["sprayed_product"] == "Copper oxychloride"
    assert case.status == Case.Status.REPORTED


# --- notification events: WhatsApp first, SMS otherwise -----------------------------


def test_prescription_event_goes_to_whatsapp_with_find_stores(chat, on_whatsapp, prescription, settings):
    settings.SMS = {**settings.SMS, "ENABLED": True}
    events.prescription_issued(prescription)
    sent = on_whatsapp.phone and list(
        __import__("apps.whatsapp.models", fromlist=["OutboundMessage"]).OutboundMessage.objects.filter(
            phone=PHONE
        )
    )
    assert sent and f"BUYRX:{prescription.code}" in ids_of(sent[-1].payload)
    assert not SmsMessage.objects.exists()


def test_event_falls_back_to_sms_outside_the_24_hour_window(on_whatsapp, prescription, settings):
    settings.SMS = {**settings.SMS, "ENABLED": True}
    Conversation.objects.filter(pk=on_whatsapp.pk).update(
        last_inbound_at=timezone.now() - timedelta(hours=25)
    )
    events.prescription_issued(prescription)
    assert SmsMessage.objects.filter(purpose=SmsMessage.Purpose.PRESCRIPTION_ISSUED).exists()


# --- buying (Module 4) ------------------------------------------------------------------


def test_find_stores_and_reserve_at_shop(chat, on_whatsapp, prescription, store_item):
    replies = chat(reply_id=f"BUYRX:{prescription.code}")
    assert f"STORE:{store_item.pk}" in ids_of(replies[-1])
    assert "PCPB (CR) 0856" in str(replies[-1])

    replies = chat(reply_id=f"STORE:{store_item.pk}")
    assert "PCPB No: PCPB (CR) 0856" in body_of(replies[-1])
    replies = chat(reply_id="PAY:shop")
    order = Order.objects.get()
    assert order.status == Order.Status.RESERVED
    assert prescription.code in body_of(replies[-1])


@responses.activate
def test_mpesa_payment_then_pickup_then_label_check(
    chat, on_whatsapp, prescription, store_item, agrovet, django_capture_on_commit_callbacks
):
    checkout = mock_stk_push()
    chat(reply_id=f"BUYRX:{prescription.code}")
    chat(reply_id=f"STORE:{store_item.pk}")
    replies = chat(reply_id="PAY:mpesa")
    assert "enter your M-Pesa PIN" in all_text(replies)
    assert Payment.objects.get().phone == "254712345678"

    with django_capture_on_commit_callbacks(execute=True):
        APIClient().post(CALLBACK_PATH, stk_callback(checkout, amount=650), format="json")
    order = Order.objects.get()
    assert order.status == Order.Status.PAID
    paid = Conversation.objects.get(phone=PHONE)
    from apps.whatsapp.models import OutboundMessage

    assert "Payment received" in body_of(OutboundMessage.objects.filter(phone=PHONE).last().payload)

    # Agrovet hands it over (sale match); the farmer is asked for the label photo.
    purchases.match_sale(agrovet_user=agrovet.user, code=prescription.code, product_id=store_item.product_id)
    paid.refresh_from_db()
    assert paid.step == "LABEL"

    responses.post(OCR_URL, json=ocr_response("RIDOMIL GOLD MZ 68 WG\nPCPB(CR) 0856"))
    replies = chat(image=sharp_photo())
    assert Verification.objects.get(type="label_check").result == "verified"
    assert "Verified genuine" in all_text(replies)
    assert balance(on_whatsapp.user) == 10
    assert Case.objects.get(pk=prescription.case_id).status == Case.Status.VERIFIED


@responses.activate
def test_cancelled_mpesa_prompt_offers_retry(
    chat, on_whatsapp, prescription, store_item, django_capture_on_commit_callbacks
):
    checkout = mock_stk_push()
    chat(reply_id=f"BUYRX:{prescription.code}")
    chat(reply_id=f"STORE:{store_item.pk}")
    chat(reply_id="PAY:mpesa")
    with django_capture_on_commit_callbacks(execute=True):
        APIClient().post(CALLBACK_PATH, stk_callback(checkout, result_code=1032), format="json")
    from apps.whatsapp.models import OutboundMessage

    last = OutboundMessage.objects.filter(phone=PHONE).last().payload
    assert f"RETRYPAY:{Order.objects.get().pk}" in ids_of(last)


def test_other_farmers_prescription_is_not_shown(chat, prescription, store_item):
    other = User.objects.create_user(username="+254722000000", phone="+254722000000", role=User.Role.FARMER)
    FarmerProfile.objects.create(
        user=other, language="en", county="Meru", ward="Nkubu", consent_at=timezone.now()
    )
    replies = chat(phone="+254722000000", reply_id=f"BUYRX:{prescription.code}")
    assert "No prescription with this code" in all_text(replies)


# --- menu, language, robustness ------------------------------------------------------------


def test_menu_words_and_language_change(chat, farmer):
    chat(text="Hi")
    replies = chat(text="menu")
    assert "REPORT" in ids_of(replies[-1])
    chat(reply_id="LANG:sw")
    assert FarmerProfile.objects.get(user=farmer).language == "sw"


def test_stale_flow_returns_to_menu(chat, farmer):
    chat(text="Hi")
    chat(reply_id="REPORT")
    Conversation.objects.filter(phone=PHONE).update(last_inbound_at=timezone.now() - timedelta(hours=3))
    replies = chat(text="hello there")
    assert Conversation.objects.get(phone=PHONE).step == "MENU" or "didn't get that" in all_text(replies)


def test_messages_have_english_and_swahili_and_fit_whatsapp_limits():
    for key, texts in MESSAGES.items():
        assert texts.get("en") and texts.get("sw"), key
        if key.startswith("btn_"):
            assert all(len(t) <= 20 for t in texts.values()), key
        if key.startswith(("row_", "started_", "weather_")) and not key.endswith("_d"):
            assert all(len(t) <= 24 for t in texts.values()), key


def test_simulator_page_and_inbox(client, chat):
    assert client.get("/whatsapp/simulator/").status_code == 200
    chat(text="Hi")
    inbox = client.get("/whatsapp/simulator/api/inbox/", {"phone": "0712345678"}).json()["messages"]
    assert [m["dir"] for m in inbox][:2] == ["in", "out"]


def test_simulator_off_in_cloud_mode(client, settings):
    settings.WHATSAPP = {**settings.WHATSAPP, "TRANSPORT": "cloud"}
    assert client.get("/whatsapp/simulator/").status_code == 404
    assert (
        client.post("/whatsapp/simulator/api/send/", {"phone": "0712345678", "text": "hi"}).status_code == 404
    )
