# AgriSense Hub — Backend

Django REST Framework API with Celery workers. See `../Documentation.md` for the system design.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements/dev.txt   # Windows; use .venv/bin on Linux/macOS
cp .env.example .env                                 # then fill in values
python manage.py migrate
python manage.py runserver
celery -A config worker -l info                      # in a second terminal (needs Redis)
```

API docs: `/api/docs/`. Tests: `pytest`. Lint: `ruff check . && ruff format --check .`

## Diagnose module — AI suggestion (process 3.1)

Uses [Kindwise crop.health](https://crop.kindwise.com/docs). Get an API key at
https://admin.kindwise.com (100 free credits; 1 credit per identification) and set `KINDWISE_API_KEY`.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/cases/{case_id}/ai-diagnosis/` | Latest AI result: top 3 suggestions, `is_plant`, `is_tomato`, `needs_retake` |
| `POST /api/v1/cases/{case_id}/ai-diagnosis/` | Queue a run (202). Farmers may re-run only after a failure or retake; staff always |

From code, Detect calls `apps.diagnosis.services.request_ai_diagnosis(case)` once a case's photos are saved.

Behaviour:
- All case photos go in one identification, downscaled to 1600px JPEG, with the case's GPS and date.
- Retries with exponential backoff on timeouts/5xx; auth (401) and out-of-credits (429) fail immediately and log at ERROR.
- One run in flight per case (DB constraint) and idempotent workers, so credits are never spent twice by redelivery.
- Non-plant or non-tomato photos set `needs_retake` and keep the case `REPORTED`. Otherwise the case moves to
  `DIAGNOSING`, including when the AI fails, because the AI only assists the agrovet.
- Provider chemical/biological treatment advice is stored but never returned by the API (registered products only).

## Module 4 — Buy Genuine Product

Needs a Daraja sandbox app (https://developer.safaricom.co.ke, test shortcode `174379`) and a free
OCR.space key (https://ocr.space/ocrapi/freekey). Set the `MPESA_*` and `OCRSPACE_API_KEY` values in `.env`.
Safaricom must reach `MPESA_CALLBACK_BASE_URL` over HTTPS; in development run `ngrok http 8000` and use its URL.
Run `celery -A config beat -l info` alongside the worker for payment reconciliation and prescription expiry.

| Endpoint | Who | Process |
|---|---|---|
| `GET /api/v1/prescriptions/{code}/stores/?latitude=&longitude=&radius_km=` | Farmer | 5.1 verified stores stocking a prescribed product, nearest first |
| `POST /api/v1/orders/` | Farmer | 5.2 order (`payment_method`: `mpesa` or `pay_at_shop`) |
| `POST /api/v1/orders/{id}/pay/` | Farmer | 5.2 STK push to the farmer's phone (202; result arrives by callback) |
| `POST /api/v1/orders/{id}/cancel/` | Farmer | Cancel an unpaid order |
| `GET /api/v1/orders/` | Farmer / agrovet | Own orders, or orders at the agrovet's store |
| `POST /api/v1/agrovet/sales/match/` | Agrovet | 5.3 scan prescription code at pickup; checks product handed over |
| `POST /api/v1/orders/{id}/label-check/` | Farmer | 5.4 label photo → PCPB number → register + prescription check |
| `GET /api/v1/rewards/` | Farmer | 5.5 points balance and history |
| `/api/v1/agrovet/store-items/` | Agrovet | Store catalogue (verified agrovets, registered products only) |
| `POST /api/v1/payments/mpesa/callback/{token}/` | Safaricom | STK callback |

Behaviour:
- **Lifecycle:** `PRESCRIBED → PURCHASED` at pickup, then `VERIFIED` (points awarded once) or `FLAGGED`
  (store excluded for that prescription; ordering elsewhere returns the case to `PRESCRIBED`). Unused
  prescriptions expire; paid orders never do.
- **Payments:** one open order per prescription and one open STK prompt per order (DB constraints). Callbacks
  are idempotent and authenticated by a secret URL token; amounts are checked against the order. Payments with
  no callback are resolved by STK query every 2 minutes, and time out after 15. Money that arrives for a cancelled
  order or with the wrong amount is marked `review` for a human.
- **Label check:** tolerant of OCR errors (B/8, O/0, missing brackets). Unreadable photos can be retaken; a
  definitive result is final. Repeated failures at one store open a `StoreFlag` for admins.
- `products`, `agrovets` and `prescriptions` are placeholders built on Documentation §9.2 for Module 3 and agrovet
  onboarding to take over.
