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

## Auth

Farmers register and log in with phone number + 4–6 digit PIN and get JWTs (`Authorization: Bearer <access>`).
Phone numbers are accepted in any common Kenyan format and stored as `+2547XXXXXXXX`. Registration requires
data-use consent. Auth endpoints are throttled per IP (`API_THROTTLE_AUTH`, default 10/min).

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register/` | `phone, pin, name, language (en/sw), county, ward, consent` → `{access, refresh}` |
| `POST /api/v1/auth/token/` | `phone, pin` → `{access, refresh}` |
| `POST /api/v1/auth/token/refresh/` | `refresh` → `{access}` |
| `GET/POST /api/v1/farms/`, `GET/PATCH /api/v1/farms/{id}/` | Farmer's farms: GPS, `size_acres`, crops |

## Detect module (process 2.0)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/cases/` | Start a report (`farm`, optional photo GPS) → `DRAFT` case |
| `POST /api/v1/cases/{id}/photos/` | Multipart `type` (`leaf`/`plant`/`stem_fruit`) + `image`. Replaces an earlier photo of that type |
| `PUT /api/v1/cases/{id}/answers/` | Quick questions: `started`, `share_affected`, `recent_weather[]`, `already_sprayed`, `sprayed_product`, `notes` |
| `POST /api/v1/cases/{id}/submit/` | Needs all 3 photos + answers → `REPORTED`, queues the AI run (202) |
| `GET /api/v1/cases/`, `GET /api/v1/cases/{id}/` | Case history; `detection` shows the photo check state |

Photo checks happen in two stages:
1. **On upload, locally (free):** resolution, darkness and blur (variance of the Laplacian). A bad photo is
   rejected with `422 {code, detail}`; `detail` is a retake prompt in the farmer's language (`apps/cases/messages.py`).
   Thresholds are in `DETECT` settings; tune `DETECT_MIN_SHARPNESS` on real field photos.
2. **After submit, via the AI run:** Kindwise decides whether the photos show a tomato plant. If not, the case's
   `detection.needs_retake` becomes true with `retake_reason` `not_plant`/`not_tomato` and a `retake_message`;
   the farmer can then replace photos and submit again (a new AI run). Otherwise Diagnose moves the case on.

The app should poll `GET /api/v1/cases/{id}/` after submitting until `detection.ai_status` is `COMPLETED` or `FAILED`.

On submit, the case takes the farm's GPS if the report had none, and copies the farmer's county/ward (for area
statistics and the outbreak alerts that will come with agrovet confirmation, process 3.4).

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
