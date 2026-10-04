import hashlib
import hmac
import json
from unittest import mock

from django.test import TestCase, override_settings

from core.models import Agrovet, Diagnosis, Farmer, Order, Product
from whatsapp.models import ChatSession

PHONE = "254722000111"
AGROVET = "254711111111"


def webhook_body(phone=PHONE, text=None, reply_id=None, image_id=None, wamid="wamid.1"):
    msg = {"from": phone, "id": wamid, "timestamp": "1700000000"}
    if text is not None:
        msg.update(type="text", text={"body": text})
    elif reply_id is not None:
        msg.update(type="interactive", interactive={"type": "button_reply",
                                                    "button_reply": {"id": reply_id, "title": "x"}})
    elif image_id is not None:
        msg.update(type="image", image={"id": image_id, "mime_type": "image/jpeg"})
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "contacts": [{"wa_id": phone, "profile": {"name": "Peter Kamau"}}],
        "messages": [msg],
    }}]}]}


@override_settings(WA_ASYNC=False, WA_APP_SECRET="", CROP_HEALTH_API_KEY="", WA_VERIFY_TOKEN="agrisense_verify",
                   MPESA_CALLBACK_TOKEN="change-me", DIAGNOSIS_REVIEW_THRESHOLD=0.5, OCRSPACE_API_KEY="")
class BotFlowTests(TestCase):
    def setUp(self):
        self.sent = []
        rec = lambda kind: (lambda to, *a, **k: self.sent.append((kind, to, a, k)) or {"ok": True})
        self.patches = [
            mock.patch("whatsapp.client.send_text", rec("text")),
            mock.patch("whatsapp.client.send_buttons", rec("buttons")),
            mock.patch("whatsapp.client.send_list", rec("list")),
            mock.patch("whatsapp.client.send_image", rec("image")),
            mock.patch("whatsapp.client.mark_read", lambda *_: {}),
            mock.patch("whatsapp.client.download_media", lambda _id: (b"\xff\xd8fake", "image/jpeg")),
            mock.patch("payments.mpesa.stk_push", lambda *a: ("ws_CO_123", None)),
        ]
        for p in self.patches:
            p.start()
        self.counter = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def send(self, **kw):
        self.counter += 1
        body = webhook_body(wamid=f"wamid.{self.counter}", **kw)
        self.sent.clear()
        r = self.client.post("/webhook/whatsapp/", data=json.dumps(body), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        return self.sent

    def last_body(self):
        return self.sent[-1][2][0]

    def register(self, language="en"):
        self.send(text="hi")
        self.send(reply_id="REG_START")
        self.send(text="peter kamau")
        self.send(reply_id="COUNTY:Tharaka-Nithi")
        self.send(text="Chuka")
        self.send(reply_id=f"LANG:{language}")
        self.send(reply_id="REG_OK")

    def shop(self):
        """Agrovet with one PCPB-registered product for blight."""
        agrovet = Agrovet.objects.create(name="Chuka Agrovet", phone=AGROVET, county="Tharaka-Nithi",
                                         town="Chuka", is_verified=True)
        product = Product.objects.create(agrovet=agrovet, name="Mancozeb", pcpb_reg_no="PCPB (CR) 1201",
                                         price=250, farmer_discount_pct=10, target_keywords="late blight, blight")
        return agrovet, product

    def texts(self):
        return " ".join(str(s[2]) for s in self.sent)

    # --- webhook plumbing ----------------------------------------------------
    def test_verify_token(self):
        ok = self.client.get("/webhook/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "agrisense_verify",
                                                    "hub.challenge": "42"})
        self.assertEqual(ok.content, b"42")
        bad = self.client.get("/webhook/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                     "hub.challenge": "42"})
        self.assertEqual(bad.status_code, 403)

    @override_settings(WA_APP_SECRET="s3cret")
    def test_signature_required(self):
        body = json.dumps(webhook_body(text="hi")).encode()
        r = self.client.post("/webhook/whatsapp/", data=body, content_type="application/json",
                             HTTP_X_HUB_SIGNATURE_256="sha256=wrong")
        self.assertEqual(r.status_code, 403)
        sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        r = self.client.post("/webhook/whatsapp/", data=body, content_type="application/json",
                             HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(r.status_code, 200)

    def test_duplicate_delivery_handled_once(self):
        body = json.dumps(webhook_body(text="hi"))
        self.client.post("/webhook/whatsapp/", data=body, content_type="application/json")
        n = len(self.sent)
        self.client.post("/webhook/whatsapp/", data=body, content_type="application/json")
        self.assertEqual(len(self.sent), n)

    # --- conversation ----------------------------------------------------------
    def test_new_farmer_gets_welcome(self):
        sent = self.send(text="Hi")
        self.assertEqual(sent[0][0], "buttons")
        self.assertIn("AgriSense", self.last_body())

    def test_registration_records_consent_and_shows_menu(self):
        self.register()
        farmer = Farmer.objects.get(phone=PHONE)
        self.assertTrue(farmer.is_registered)
        self.assertEqual(farmer.county, "Tharaka-Nithi")
        self.assertEqual(farmer.main_crops, "tomato")
        self.assertIsNotNone(farmer.consent_at)
        self.assertEqual(self.sent[-1][0], "list")  # main menu

    def test_swahili_farmer_gets_swahili(self):
        self.register(language="sw")
        self.send(reply_id="DIAG")
        self.assertIn("Tuma *picha moja", self.last_body())

    def test_full_demo_story(self):
        """Photo -> AI suggestion -> agrovet confirms -> buy registered product -> M-Pesa -> hand-over -> label."""
        self.register()
        agrovet, product = self.shop()
        self.send(reply_id="DIAG")
        sent = self.send(image_id="media123")

        d = Diagnosis.objects.get()
        self.assertEqual(d.disease, "Late blight")
        self.assertEqual(d.status, Diagnosis.STATUS_REVIEW)  # never final without an agrovet
        self.assertTrue(any(s[1] == AGROVET for s in sent))  # agrovet asked to review
        self.assertIn("AI suggestion", self.texts())
        self.assertNotIn("Chemical", self.texts())  # provider chemical advice is never shown

        # Buying is blocked until the agrovet confirms.
        self.send(reply_id=f"BUY:{d.pk}")
        self.assertNotIn("PROD:", self.texts())

        self.send(phone=AGROVET, reply_id=f"REV_OK:{d.pk}")
        d.refresh_from_db()
        self.assertEqual(d.status, Diagnosis.STATUS_CONFIRMED)
        self.assertIn("Confirmed by Chuka Agrovet", self.texts())

        sent = self.send(reply_id=f"BUY:{d.pk}")
        rows = sent[-1][2][2][0][1]
        self.assertEqual(rows[0][0], f"PROD:{product.pk}")
        self.assertIn("PCPB (CR) 1201", rows[0][2])
        self.send(reply_id=f"PROD:{product.pk}")
        self.assertIn("PCPB No: PCPB (CR) 1201", self.last_body())
        self.send(reply_id="QTY:2")
        self.send(reply_id="PAY_ME")
        order = Order.objects.get()
        self.assertEqual(order.amount, 450)  # 225 x 2 after discount

        callback = {"Body": {"stkCallback": {
            "CheckoutRequestID": "ws_CO_123", "ResultCode": 0, "ResultDesc": "ok",
            "CallbackMetadata": {"Item": [{"Name": "MpesaReceiptNumber", "Value": "SGH12345"}]},
        }}}
        self.sent.clear()
        self.client.post("/payments/mpesa/callback/change-me/", data=json.dumps(callback),
                         content_type="application/json")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertTrue(any(s[1] == AGROVET and f"HANDOVER:{order.pk}" in str(s) for s in self.sent))

        self.send(phone=AGROVET, reply_id=f"HANDOVER:{order.pk}")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COLLECTED)
        self.assertIn("photo of the product *label*", self.texts())

        self.send(text="I see PCPB(CR)1201 on it")
        order.refresh_from_db()
        self.assertEqual(order.label_result, Order.LABEL_VERIFIED)
        self.assertIn("Verified genuine", self.last_body())
        self.assertEqual(Farmer.objects.get(phone=PHONE).points, 10)

    def test_fake_label_is_flagged(self):
        self.register()
        agrovet, product = self.shop()
        order = Order.objects.create(farmer=Farmer.objects.get(phone=PHONE), product=product, amount=225,
                                     pay_phone=PHONE, status=Order.STATUS_PAID)
        self.send(phone=AGROVET, reply_id=f"HANDOVER:{order.pk}")
        sent = self.send(text="PCPB (CR) 9999")
        order.refresh_from_db()
        self.assertEqual(order.label_result, Order.LABEL_NOT_REGISTERED)
        self.assertIn("Do not use it", self.texts())
        self.assertTrue(any(s[1] == AGROVET for s in sent))  # store told
        self.assertEqual(Farmer.objects.get(phone=PHONE).points, 0)

    def test_unreadable_label_can_be_retried(self):
        self.register()
        agrovet, product = self.shop()
        order = Order.objects.create(farmer=Farmer.objects.get(phone=PHONE), product=product, amount=225,
                                     pay_phone=PHONE, status=Order.STATUS_PAID)
        self.send(phone=AGROVET, reply_id=f"HANDOVER:{order.pk}")
        self.send(image_id="label1")  # no OCR key in tests, so the photo cannot be read
        self.assertIn("read a PCPB number", self.last_body())
        self.send(text="PCPB (CR) 1201")
        order.refresh_from_db()
        self.assertEqual(order.label_result, Order.LABEL_VERIFIED)

    def test_unpaid_order_cannot_be_handed_over(self):
        self.register()
        agrovet, product = self.shop()
        order = Order.objects.create(farmer=Farmer.objects.get(phone=PHONE), product=product, amount=225,
                                     pay_phone=PHONE)
        self.send(phone=AGROVET, reply_id=f"HANDOVER:{order.pk}")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_callback_wrong_token_404(self):
        r = self.client.post("/payments/mpesa/callback/guess/", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_agrovet_corrects_ai(self):
        self.register()
        self.shop()
        self.send(reply_id="DIAG")
        self.send(image_id="media123")
        d = Diagnosis.objects.get()
        self.send(phone=AGROVET, reply_id=f"REV_FIX:{d.pk}")
        sent = self.send(phone=AGROVET, text="Early blight - remove lower leaves")
        d.refresh_from_db()
        self.assertEqual(d.disease, "Early blight")
        self.assertEqual(d.status, Diagnosis.STATUS_REJECTED)
        self.assertTrue(any(s[1] == PHONE for s in sent))  # farmer told

    def test_outcome_button(self):
        self.register()
        farmer = Farmer.objects.get(phone=PHONE)
        d = Diagnosis.objects.create(farmer=farmer, crop="tomato", disease="Late blight", confidence=0.9)
        self.send(reply_id=f"OUT:{d.pk}:worked")
        d.refresh_from_db()
        self.assertEqual(d.outcome, "worked")

    def test_menu_word_resets_flow(self):
        self.register()
        self.send(reply_id="DIAG")
        self.send(text="menu")
        self.assertEqual(ChatSession.objects.get(phone=PHONE).step, "MAIN_MENU")
