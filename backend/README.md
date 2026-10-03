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
