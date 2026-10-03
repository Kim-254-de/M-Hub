"""Base settings shared by every environment.

All environment-specific values are read from environment variables (or a
local ``.env`` file in development). Nothing secret is hard-coded here.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

# --- Core -------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.cases",
    "apps.diagnosis",
    # Placeholders built against Documentation §9.2; owned by the Prescribe/agrovet work.
    "apps.products",
    "apps.agrovets",
    "apps.prescriptions",
    # Module 4: Buy Genuine Product
    "apps.purchases",
    "apps.rewards",
    "apps.notifications",
    "apps.followups",
    # Reviewed translations of farmer-facing text (Kikuyu first)
    "apps.translations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache ------------------------------------------------------------------
# Used for the M-Pesa OAuth token. Use Redis in production so all workers share it.

CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

# --- Auth -------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N -------------------------------------------------------------------

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# Farmer languages without their own text fall back to these, then English (apps.translations).
# Kikuyu speakers in the pilot area read Kiswahili.
LANGUAGE_FALLBACKS = {"ki": ["sw"]}

# --- Static and media -------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = env.path("DJANGO_MEDIA_ROOT", default=BASE_DIR / "media")

# Case photos are capped at upload time; this is the hard limit on request size.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Django REST Framework --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT for the mobile app; sessions for the admin and browsable API.
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("API_THROTTLE_USER", default="120/min"),
        "ai_diagnosis_retry": env("API_THROTTLE_AI_RETRY", default="10/hour"),
        # Registration and login, per client IP. PINs are short, so keep this tight.
        "auth": env("API_THROTTLE_AUTH", default="10/min"),
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=30)),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AgriSense Hub API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "CaseStatusEnum": "apps.cases.models.Case.Status",
        "AgrovetReviewStatusEnum": "apps.diagnosis.models.AgrovetReview.Status",
        "ShareAffectedEnum": "apps.followups.models.ShareAffected",
    },
}

# --- Celery -----------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 90
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "reconcile-mpesa-payments": {
        "task": "apps.purchases.tasks.reconcile_pending_payments_task",
        "schedule": 120.0,
    },
    "expire-prescriptions": {
        "task": "apps.purchases.tasks.expire_prescriptions_task",
        "schedule": 15 * 60.0,
    },
    "assign-agrovet-reviews": {
        "task": "apps.diagnosis.tasks.assign_reviews_task",
        "schedule": 10 * 60.0,
    },
    "review-prescribing-patterns": {
        "task": "apps.prescriptions.tasks.review_prescribing_patterns_task",
        "schedule": 24 * 60 * 60.0,
    },
}

# --- Diagnosis provider (Kindwise crop.health) ------------------------------
# https://crop.kindwise.com/docs

DIAGNOSIS = {
    "PROVIDER": env("DIAGNOSIS_PROVIDER", default="kindwise"),
    "KINDWISE_API_KEY": env("KINDWISE_API_KEY", default=""),
    "KINDWISE_BASE_URL": env("KINDWISE_BASE_URL", default="https://crop.kindwise.com/api/v1"),
    # (connect, read) seconds. Identification is synchronous and usually < 5s.
    "KINDWISE_TIMEOUT": (
        env.float("KINDWISE_CONNECT_TIMEOUT", default=5.0),
        env.float("KINDWISE_READ_TIMEOUT", default=45.0),
    ),
    # Language for details (ISO 639-1). Kindwise omits its own description,
    # symptoms and treatment fields when several languages are requested, so
    # exactly one is used; translation for farmers happens downstream.
    "KINDWISE_LANGUAGE": env("KINDWISE_LANGUAGE", default="en"),
    # Representative similar images (licensed; citation must be shown) to help agrovets review.
    "KINDWISE_SIMILAR_IMAGES": env.bool("KINDWISE_SIMILAR_IMAGES", default=True),
    # Photos are downscaled before upload to save farmer bandwidth and provider latency.
    "MAX_IMAGE_DIMENSION": env.int("DIAGNOSIS_MAX_IMAGE_DIMENSION", default=1600),
    # How many disease suggestions to keep per identification (spec: top 3).
    "TOP_N": env.int("DIAGNOSIS_TOP_N", default=3),
    # Below this is_plant probability, the photos are treated as not a plant.
    "MIN_IS_PLANT_PROBABILITY": env.float("DIAGNOSIS_MIN_IS_PLANT", default=0.5),
    # Minimum probability for the crop to be accepted as tomato.
    "MIN_TOMATO_PROBABILITY": env.float("DIAGNOSIS_MIN_TOMATO", default=0.3),
    "MAX_ATTEMPTS": env.int("DIAGNOSIS_MAX_ATTEMPTS", default=5),
}

# --- Diagnose: agrovet confirmation (processes 3.2-3.6) -----------------------

DIAGNOSE = {
    # 3.2 Similar past cases: confirmed cases in the same ward or within this distance, this recent.
    "SIMILAR_CASES_RADIUS_KM": env.float("DIAGNOSE_SIMILAR_RADIUS_KM", default=15.0),
    "SIMILAR_CASES_WINDOW_DAYS": env.int("DIAGNOSE_SIMILAR_WINDOW_DAYS", default=30),
    # The similar-case majority only counts in the agreement check with at least this many cases.
    "SIMILAR_CASES_MIN_FOR_AGREEMENT": env.int("DIAGNOSE_SIMILAR_MIN_CASES", default=3),
    # The AI top suggestion only counts in the agreement check at or above this probability.
    "AI_MIN_PROBABILITY_FOR_AGREEMENT": env.float("DIAGNOSE_AI_MIN_PROBABILITY", default=0.5),
    # Below this, the farmer's provisional result says the AI is not sure instead of naming a disease.
    "AI_MIN_PROBABILITY_FOR_PROVISIONAL": env.float("DIAGNOSE_AI_PROVISIONAL_MIN_PROBABILITY", default=0.5),
    # 3.3 Peer input: farmers in the case's ward with at least this many verified purchases.
    "PEER_MIN_VERIFIED_PURCHASES": env.int("DIAGNOSE_PEER_MIN_VERIFIED", default=1),
    # 3.4/3.6 An unanswered review is withdrawn and the case goes to the next nearest agrovet.
    "REVIEW_TIMEOUT_HOURS": env.int("DIAGNOSE_REVIEW_TIMEOUT_HOURS", default=24),
}

# --- Prescribe (processes 4.1-4.5) --------------------------------------------

PRESCRIBE = {
    "EXPIRY_DAYS": env.int("PRESCRIBE_EXPIRY_DAYS", default=14),
    # 4.2 Local evidence: outcomes from verified purchases this close and this recent.
    "MIN_LOCAL_OUTCOMES": env.int("PRESCRIBE_MIN_LOCAL_OUTCOMES", default=5),
    "OUTCOME_RADIUS_KM": env.float("PRESCRIBE_OUTCOME_RADIUS_KM", default=15.0),
    "OUTCOME_WINDOW_DAYS": env.int("PRESCRIBE_OUTCOME_WINDOW_DAYS", default=365),
    # Conflict of interest: an agrovet who, in at least MIN prescriptions over the window, picks a
    # pricier option over a better-performing one at least SHARE of the time loses trust.
    "COI_WINDOW_DAYS": env.int("PRESCRIBE_COI_WINDOW_DAYS", default=90),
    "COI_MIN_PRESCRIPTIONS": env.int("PRESCRIBE_COI_MIN_PRESCRIPTIONS", default=5),
    "COI_SHARE": env.float("PRESCRIBE_COI_SHARE", default=0.6),
}

# --- SMS (Africa's Talking) -----------------------------------------------------
# https://developers.africastalking.com/docs/sms/overview
# Sandbox: username "sandbox"; messages show in the simulator, not on real phones.

AT_API_KEY = env("AT_API_KEY", default="")
SMS = {
    # On when an API key is set; SMS_ENABLED=false turns it off explicitly.
    "ENABLED": env.bool("SMS_ENABLED", default=bool(AT_API_KEY)),
    "AT_BASE_URL": env("AT_BASE_URL", default="https://api.sandbox.africastalking.com"),
    "AT_USERNAME": env("AT_USERNAME", default="sandbox"),
    "AT_API_KEY": AT_API_KEY,
    # Approved alphanumeric sender ID or shortcode. Empty uses Africa's Talking's default.
    "AT_SENDER_ID": env("AT_SENDER_ID", default=""),
    "TIMEOUT": (env.float("SMS_CONNECT_TIMEOUT", default=5.0), env.float("SMS_READ_TIMEOUT", default=30.0)),
    "MAX_ATTEMPTS": env.int("SMS_MAX_ATTEMPTS", default=5),
    # Secret path segment for the delivery report URL (Africa's Talking does not sign reports).
    "CALLBACK_TOKEN": env("SMS_CALLBACK_TOKEN", default=""),
}

# --- Apply and Follow-up -----------------------------------------------------------

FOLLOWUP = {
    # Days after spraying on which the farmer reports; the last one is the outcome.
    "CHECK_IN_DAYS": [2, 4, 7],
    # No check-ins after this many days: late recollections are not evidence.
    "CLOSE_AFTER_DAYS": env.int("FOLLOWUP_CLOSE_AFTER_DAYS", default=14),
    # Points for completing the follow-up, so farmers keep reporting when a product fails too.
    "REWARD_POINTS": env.int("FOLLOWUP_REWARD_POINTS", default=5),
}

# --- Trust scores (Documentation §6.5) -----------------------------------------

TRUST = {
    "DIAGNOSIS_CONFIRMED": env.float("TRUST_DIAGNOSIS_CONFIRMED", default=1.0),
    "DIAGNOSIS_CONTRADICTED": env.float("TRUST_DIAGNOSIS_CONTRADICTED", default=-2.0),
    "PRESCRIBING_PATTERN": env.float("TRUST_PRESCRIBING_PATTERN", default=-5.0),
    "VERIFIED_PURCHASE": env.float("TRUST_VERIFIED_PURCHASE", default=1.0),
}

# --- Detect (photo capture) ------------------------------------------------
# Local checks run on upload, before any provider credit is spent. The
# plant/tomato check comes from the AI diagnosis run (needs_retake).

DETECT = {
    # Shortest side in pixels. Phone cameras are far above this; it catches thumbnails and screenshots.
    "MIN_PHOTO_SIDE": env.int("DETECT_MIN_PHOTO_SIDE", default=480),
    # Variance of the Laplacian on a greyscale copy scaled to ANALYSIS_SIZE. Lower means blurrier.
    # Tune on real field photos; values well under 100 are usually out of focus or shaken.
    "MIN_SHARPNESS": env.float("DETECT_MIN_SHARPNESS", default=60.0),
    # Mean greyscale brightness, 0-255.
    "MIN_BRIGHTNESS": env.float("DETECT_MIN_BRIGHTNESS", default=40.0),
    "ANALYSIS_SIZE": env.int("DETECT_ANALYSIS_SIZE", default=1024),
    "MAX_PHOTO_BYTES": env.int("DETECT_MAX_PHOTO_BYTES", default=10 * 1024 * 1024),
}

# --- M-Pesa Daraja (STK push) -----------------------------------------------
# https://developer.safaricom.co.ke/apis/MpesaExpressSimulate

MPESA = {
    "BASE_URL": env("MPESA_BASE_URL", default="https://sandbox.safaricom.co.ke"),
    "CONSUMER_KEY": env("MPESA_CONSUMER_KEY", default=""),
    "CONSUMER_SECRET": env("MPESA_CONSUMER_SECRET", default=""),
    "SHORTCODE": env("MPESA_SHORTCODE", default=""),
    "PASSKEY": env("MPESA_PASSKEY", default=""),
    # CustomerPayBillOnline for a Paybill, CustomerBuyGoodsOnline for a Till.
    "TRANSACTION_TYPE": env("MPESA_TRANSACTION_TYPE", default="CustomerPayBillOnline"),
    # For a Till, PartyB is the till number; for a Paybill it equals SHORTCODE.
    "PARTY_B": env("MPESA_PARTY_B", default=""),
    # Public HTTPS base URL Safaricom can reach (e.g. an ngrok URL in development).
    "CALLBACK_BASE_URL": env("MPESA_CALLBACK_BASE_URL", default=""),
    # Daraja does not sign callbacks; a secret path segment authenticates them.
    "CALLBACK_TOKEN": env("MPESA_CALLBACK_TOKEN", default=""),
    "TIMEOUT": (
        env.float("MPESA_CONNECT_TIMEOUT", default=5.0),
        env.float("MPESA_READ_TIMEOUT", default=30.0),
    ),
}

# --- Label OCR (OCR.space) ---------------------------------------------------
# https://ocr.space/ocrapi

OCR = {
    "PROVIDER": env("OCR_PROVIDER", default="ocrspace"),
    "OCRSPACE_API_KEY": env("OCRSPACE_API_KEY", default=""),
    "OCRSPACE_URL": env("OCRSPACE_URL", default="https://api.ocr.space/parse/image"),
    # Engine 2 handles mixed fonts and auto-rotation well; 3 is more accurate but slower.
    "OCRSPACE_ENGINE": env.int("OCRSPACE_ENGINE", default=2),
    "TIMEOUT": (env.float("OCR_CONNECT_TIMEOUT", default=5.0), env.float("OCR_READ_TIMEOUT", default=30.0)),
    # Free tier rejects files over 1 MB.
    "MAX_UPLOAD_BYTES": env.int("OCR_MAX_UPLOAD_BYTES", default=1024 * 1024),
}

# --- Module 4: Buy Genuine Product -----------------------------------------

PURCHASES = {
    "DEFAULT_STORE_RADIUS_KM": env.float("PURCHASES_STORE_RADIUS_KM", default=30.0),
    "MAX_STORE_RESULTS": env.int("PURCHASES_MAX_STORE_RESULTS", default=20),
    "REWARD_POINTS_VERIFIED_PURCHASE": env.int("REWARD_POINTS_VERIFIED_PURCHASE", default=10),
    # Failed label checks for one store within the window that open a store flag.
    "STORE_FLAG_THRESHOLD": env.int("PURCHASES_STORE_FLAG_THRESHOLD", default=3),
    "STORE_FLAG_WINDOW_DAYS": env.int("PURCHASES_STORE_FLAG_WINDOW_DAYS", default=90),
    # Query Daraja for STK payments with no callback after this many seconds.
    "PAYMENT_RECONCILE_AFTER_SECONDS": env.int("PURCHASES_PAYMENT_RECONCILE_AFTER", default=90),
    # Give up on an STK payment that is still unresolved after this long.
    "PAYMENT_TIMEOUT_MINUTES": env.int("PURCHASES_PAYMENT_TIMEOUT_MINUTES", default=15),
    "MAX_LABEL_PHOTO_BYTES": env.int("PURCHASES_MAX_LABEL_PHOTO_BYTES", default=10 * 1024 * 1024),
}

# --- Logging ----------------------------------------------------------------

LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
