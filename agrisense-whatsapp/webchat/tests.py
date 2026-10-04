from django.test import TestCase, override_settings

from core.models import Agrovet, Order, Product
from webchat.models import WebMessage

PHONE = "254712345678"


@override_settings(WA_TRANSPORT="web", CROP_HEALTH_API_KEY="", MPESA_CONSUMER_KEY="", MPESA_PASSKEY="")
class WebChatTests(TestCase):
    def say(self, **fields):
        r = self.client.post("/chat/api/send/", {"phone": PHONE, "name": "Peter Kamau", **fields})
        self.assertEqual(r.status_code, 200, r.content)

    def outbox(self):
        r = self.client.get("/chat/api/inbox/", {"phone": PHONE, "after": 0})
        return [m for m in r.json()["messages"] if m["dir"] == "out"]

    def test_page_loads(self):
        self.assertEqual(self.client.get("/chat/").status_code, 200)

    @override_settings(WA_TRANSPORT="cloud")
    def test_page_hidden_when_using_real_whatsapp(self):
        self.assertEqual(self.client.get("/chat/").status_code, 404)

    def test_hi_gets_welcome_buttons(self):
        self.say(text="Hi")
        out = self.outbox()
        self.assertEqual(out[0]["payload"]["type"], "interactive")
        self.assertEqual(out[0]["payload"]["interactive"]["action"]["buttons"][0]["reply"]["id"], "REG_START")

    def test_simulated_mpesa_prompt_and_payment(self):
        for f in [dict(text="hi"), dict(reply_id="REG_START"), dict(text="Peter Kamau"),
                  dict(reply_id="COUNTY:Meru"), dict(text="Nkubu"),
                  dict(reply_id="LANG:en"), dict(reply_id="REG_OK")]:
            self.say(**f)
        a = Agrovet.objects.create(name="Meru Agro", phone="254711000000", county="Meru", town="Nkubu", is_verified=True)
        p = Product.objects.create(agrovet=a, name="Mancozeb", pcpb_reg_no="PCPB (CR) 1201", price=300,
                                   target_keywords="blight")
        from core.models import Diagnosis, Farmer
        d = Diagnosis.objects.create(farmer=Farmer.objects.get(phone=PHONE), crop="tomato", disease="Late blight", confidence=.9,
                                     status=Diagnosis.STATUS_CONFIRMED)
        for f in [dict(reply_id=f"BUY:{d.pk}"), dict(reply_id=f"PROD:{p.pk}"), dict(reply_id="QTY:1"), dict(reply_id="PAY_ME")]:
            self.say(**f)
        stk = WebMessage.objects.get(direction=WebMessage.STK)
        self.client.post("/chat/api/stk/", {"checkout_id": stk.payload["checkout_id"], "action": "ok"})
        order = Order.objects.get()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertTrue(any(order.pickup_code in str(m["payload"]) for m in self.outbox()))
