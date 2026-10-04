# AgriSense Hub — WhatsApp bot

Farmers chat with AgriSense on WhatsApp the same way you register with Britam:
a welcome message with buttons, a short sign-up chat, then a menu.

```
Hi ─► Welcome [Register] [How it works]
        └─► name → county (list) → ward → language (English / Kiswahili) → [Confirm + data consent]
              └─► MAIN MENU (list)
                    ├─ 🔍 Check my tomato → send photo
                    │      └─► 🤖 AI suggestion + prevention tips (never final)
                    │            └─► agrovet phone: [✅ Correct] [📝 Correct it]
                    │                  └─► farmer: ✅ "Confirmed by Chuka Farmers Agrovet" [Buy treatment]
                    │                        → PCPB-registered products only (PCPB No shown)
                    │                        → quantity → [Pay with M-Pesa] → STK push
                    │                        → ✅ receipt + pickup code
                    │                        → agrovet phone: [✅ Handed over]
                    │                        → farmer: 📷 photo of the label (or type the PCPB No)
                    │                        → ✅ Verified genuine +10 points  /  ⚠️ Not registered  /  ⚠️ Not prescribed
                    ├─ 📋 My history
                    ├─ 🏪 Agrovets near me
                    ├─ 👤 My profile (points, edit, change language)
                    └─ ❓ Help
Later: "Did the treatment work?" [Yes] [Partly] [No change]  → stored for agrovet verification
```

This follows Documentation.md: the pilot is **tomato only**, **every** AI result is confirmed by a
verified agrovet before the farmer can buy, the AI's chemical advice is never shown (only prevention
steps), only products with a PCPB number are offered, and the label is checked after pickup.

### Demo script (two phones at http://localhost:8000/chat/)

1. Farmer: **Hi → Register** → name, county *Tharaka-Nithi*, ward → **English** → **Confirm**.
2. Farmer: **Check my tomato** → send a leaf photo → sees the AI suggestion and "an agrovet is checking".
3. Agrovet phone: review request with the photo → **✅ Correct**.
4. Farmer: "✅ Confirmed by …" → **Buy treatment** → pick a product (PCPB No shown) → **1** → **Pay with this no.**
   → enter any 4 digits on the M-Pesa prompt → receipt + pickup code.
5. Agrovet phone: "New paid order" → **✅ Handed over**.
6. Farmer: send a photo of the label, or type the number shown on the product card, e.g. `PCPB (CR) 1201`
   → **✅ Verified genuine, +10 points**. Type `PCPB (CR) 9999` instead to show a fake product being caught.

The PCPB numbers created by `seed_demo` are **demo values**, not real registrations.
With `OCRSPACE_API_KEY` set, label photos are read by OCR; without it, the farmer types the number.

## Project layout

| Path | What it does |
|---|---|
| `whatsapp/views.py` | Webhook: Meta verification (GET), signature check, de-duplication, background processing |
| `whatsapp/flow.py` | The conversation state machine (registration, menu, diagnose, shop, pay, agrovet review) |
| `whatsapp/messages.py` | Every farmer-facing sentence, in English (`EN`) and Kiswahili (`SW`) |
| `whatsapp/client.py` | WhatsApp Cloud API calls (text, buttons, lists, images, templates, media download) |
| `whatsapp/notify.py` | Messages the system sends by itself (payment result, review requests, follow-ups) |
| `core/models.py` | Farmer, Agrovet, Product, Diagnosis, Order |
| `core/services/crop_health.py` | Kindwise crop.health API (demo mode when no key) |
| `core/services/label_check.py` | PCPB number check of label photos (OCR.space) or typed numbers |
| `payments/mpesa.py`, `payments/views.py` | Daraja STK push and callback |
| `core/api.py` | Read-only REST API for the mobile app (`/api/products/`, `/api/agrovets/`, `/api/diagnoses/`) |
| `core/management/commands/` | `chat` (terminal simulator), `seed_demo`, `send_followups` |

## 0. Browser chat (phone-style demo on the real backend)

```bat
python manage.py runserver 8000
```

Open **http://localhost:8000/chat/**. You get two phones side by side, a **farmer** and an
**agrovet**, chatting with AgriSense Hub in a messaging-app interface: tappable buttons, menu
lists, photo upload (📎 or 📷), typing indicator, read ticks, and an M-Pesa PIN prompt on payment.
Every reply comes from the real bot engine (`whatsapp/flow.py`) and is saved in the database,
so the admin at `/admin/` shows the same farmers, diagnoses and orders.

- **Restart** (top right) clears both phones to start the demo again.
- `/chat/?single=1` shows just the farmer phone full screen. Open it on a real phone via ngrok.
- `/chat/?farmer=0722000111&name=Jane%20Wanjiru` changes the farmer.
- The agrovet phone is the first verified agrovet, so run `seed_demo --agrovet-phone <number>` first.

The browser chat is on while `WA_TRANSPORT=web`, which is the default until you set
`WA_ACCESS_TOKEN`. Set `WA_TRANSPORT=cloud` to send through real WhatsApp. `/chat/` then switches off.
Without Daraja keys, payments use the on-screen PIN prompt. Any 4 digits work, and no money moves.

## 1. Run it locally (no Meta account needed yet)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
python manage.py migrate
python manage.py seed_demo --agrovet-phone 2547XXXXXXXX   # your 2nd number = demo agrovet
python manage.py createsuperuser
python manage.py chat 0712345678
```

`chat` lets you talk to the bot in the terminal. Type `hi`, tap buttons with `#ID`
(e.g. `#REG_START`, `#DIAG`), send a photo with `/photo C:\path\leaf.jpg`,
and finish a payment with `/paid`.

Run the tests: `python manage.py test`

## 2. Connect it to WhatsApp

1. Start the server: `python manage.py runserver 8000`
2. In another terminal: `ngrok http 8000` → copy the `https://….ngrok-free.app` address.
3. Put it in `.env` as `PUBLIC_BASE_URL` and `DJANGO_CSRF_TRUSTED_ORIGINS`, and fill in
   `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`. Restart the server.
4. Meta dashboard → your app → **Use cases → Customize → Configuration → Webhook**:
   - Callback URL: `https://….ngrok-free.app/webhook/whatsapp/`
   - Verify token: same as `WA_VERIFY_TOKEN`
   - Click **Verify and save**, then subscribe to the **messages** field.
5. From your phone (one of the verified test recipients), send **Hi** to the test number.

> With Meta's test number the bot can only message the (max 5) numbers in the
> recipient list — add your agrovet demo phone there too.

## 3. crop.health

Get an API key at crop.kindwise.com and set `CROP_HEALTH_API_KEY`. Without it, the bot
returns a demo diagnosis so you can still show the whole flow.

## 4. M-Pesa

Use the Daraja sandbox (developer.safaricom.co.ke): create an app, copy the consumer
key/secret, and the Lipa na M-Pesa Online passkey for shortcode 174379. The callback URL is
built automatically: `PUBLIC_BASE_URL/payments/mpesa/callback/<MPESA_CALLBACK_TOKEN>/`.

## 5. Deploy on Render

Push to GitHub, then **New → Blueprint** and select the repo — `render.yaml` creates the web
service and a Postgres database. Fill the `sync: false` variables in the Render dashboard,
set `PUBLIC_BASE_URL` to the Render URL, and point the Meta webhook at
`https://<service>.onrender.com/webhook/whatsapp/`.

Daily follow-ups: add a Render cron job running `python manage.py send_followups --days 7`.
It uses a template you must create in **WhatsApp Manager → Message templates**:

- Name `treatment_followup`, category **Utility**, language English
- Body: `Hi {{1}}, did the treatment for {{2}} on your {{3}} work?`
- Quick reply buttons: `Yes, it worked`, `Partly`, `No change`

## Notes before going beyond the hackathon

- **Kiswahili:** have a native speaker review `SW` in `whatsapp/messages.py`; text-to-speech
  voice notes can be added in `notify.py`/`flow.py` later.
- **Photos** are stored on the server disk and served at `/media/` so agrovets can see them. Render's
  disk is wiped on redeploy — move to Cloudinary/S3 for production.
- **`/api/diagnoses/?phone=`** has no authentication yet — add token auth before real farmer data goes in.
- Agrovets can only receive review requests in WhatsApp if they messaged the bot in the last 24 hours
  (Meta rule). Otherwise they review in the admin at `/admin/` — saving a diagnosis as
  *Confirmed* / *Corrected* notifies the farmer automatically.
