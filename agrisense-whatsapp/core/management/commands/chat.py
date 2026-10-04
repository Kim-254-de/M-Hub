"""python manage.py chat 0712345678

Talk to the bot in your terminal — no Meta account needed. Bot replies are
printed instead of sent to WhatsApp. Commands:
  <text>            send a text message
  #ID               tap a button / list row, e.g. #REG_START, #DIAG, #QTY:1
  /photo PATH       send a photo from your computer
  /paid             simulate a successful M-Pesa callback for the last order
  /quit             exit
"""
import uuid
from pathlib import Path
from unittest import mock

from django.core.management.base import BaseCommand

from core.models import Order
from core.utils import normalize_phone
from whatsapp import client, flow, notify


def _print_text(to, body, *a, **k):
    print(f"\n🤖 → {to}\n{body}\n")
    return {"ok": True}


def _print_buttons(to, body, buttons, header=None, footer=None):
    print(f"\n🤖 → {to}" + (f"  [{header}]" if header else ""))
    print(body)
    print("   " + "   ".join(f"[{title}] #{bid}" for bid, title in buttons))
    if footer:
        print(f"   _{footer}_")
    print()
    return {"ok": True}


def _print_list(to, body, button_label, sections, header=None, footer=None):
    print(f"\n🤖 → {to}" + (f"  [{header}]" if header else ""))
    print(body)
    print(f"   ☰ {button_label}")
    for title, rows in sections:
        print(f"   — {title}")
        for rid, rtitle, *rest in rows:
            desc = f"  ({rest[0]})" if rest and rest[0] else ""
            print(f"      #{rid}  {rtitle}{desc}")
    print()
    return {"ok": True}


def _print_image(to, link, caption=""):
    print(f"\n🤖 → {to}  🖼️ {link}\n{caption}\n")
    return {"ok": True}


def _print_template(to, name, lang="en", body_params=None, button_payloads=None):
    print(f"\n🤖 → {to}  📨 template '{name}' {body_params} buttons: {button_payloads}\n")
    return {"ok": True}


class Command(BaseCommand):
    help = "Chat with the AgriSense WhatsApp bot from the terminal (offline simulator)."

    def add_arguments(self, parser):
        parser.add_argument("phone")
        parser.add_argument("--name", default="Test Farmer")

    def handle(self, *args, **opts):
        phone = normalize_phone(opts["phone"]) or opts["phone"]
        photos = {}

        def fake_download(media_id):
            path = photos.get(media_id)
            return (Path(path).read_bytes(), "image/jpeg") if path else (None, None)

        def fake_stk(phone_, amount, ref, desc):
            print(f"   💳 (simulated STK push KES {amount} to {phone_} — type /paid to complete)")
            return f"ws_CO_{uuid.uuid4().hex[:12]}", None

        patches = [
            mock.patch.object(client, "send_text", _print_text),
            mock.patch.object(client, "send_buttons", _print_buttons),
            mock.patch.object(client, "send_list", _print_list),
            mock.patch.object(client, "send_image", _print_image),
            mock.patch.object(client, "send_template", _print_template),
            mock.patch.object(client, "mark_read", lambda *_: {}),
            mock.patch.object(client, "download_media", fake_download),
            mock.patch("payments.mpesa.stk_push", fake_stk),
        ]
        for p in patches:
            p.start()
        self.stdout.write("AgriSense simulator. Type 'hi' to start, #ID to tap a button, /quit to exit.\n")
        try:
            while True:
                try:
                    line = input(f"📱 {phone}> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line:
                    continue
                if line == "/quit":
                    break
                msg = flow.Incoming(phone=phone, wamid=uuid.uuid4().hex, name=opts["name"])
                if line.startswith("#"):
                    msg.kind, msg.reply_id = "reply", line[1:]
                elif line.startswith("/photo"):
                    path = line[len("/photo"):].strip()
                    if not Path(path).is_file():
                        print("   File not found.")
                        continue
                    media_id = uuid.uuid4().hex
                    photos[media_id] = path
                    msg.kind, msg.media_id, msg.mime = "image", media_id, "image/jpeg"
                elif line == "/paid":
                    order = Order.objects.filter(farmer__phone=phone).first()
                    if not order:
                        print("   No order yet.")
                        continue
                    order.status, order.mpesa_receipt = Order.STATUS_PAID, "SIM" + uuid.uuid4().hex[:7].upper()
                    order.save()
                    notify.order_paid(order)
                    continue
                else:
                    msg.text = line
                flow.handle(msg)
        finally:
            for p in patches:
                p.stop()
