"""Base settings shared by every environment.

All environment-specific values are read from environment variables (or a
local ``.env`` file in development). Nothing secret is hard-coded here.
"""

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
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AgriSense Hub API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
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
