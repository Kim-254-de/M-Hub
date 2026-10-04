"""AgriSense Hub — WhatsApp bot backend settings.

Everything secret or environment-specific comes from environment variables
(see .env.example). Locally, a .env file in the project root is loaded.
"""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key, default=""):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return env(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "whatsapp",
    "payments",
    "webchat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "agrisense.urls"

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

WSGI_APPLICATION = "agrisense.wsgi.application"

# An empty DATABASE_URL in .env falls back to SQLite (dj_database_url treats "" as "no database").
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# --- WhatsApp Cloud API (Meta) -------------------------------------------
WA_ACCESS_TOKEN = env("WA_ACCESS_TOKEN")
WA_PHONE_NUMBER_ID = env("WA_PHONE_NUMBER_ID")
WA_BUSINESS_ACCOUNT_ID = env("WA_BUSINESS_ACCOUNT_ID")
WA_VERIFY_TOKEN = env("WA_VERIFY_TOKEN", "agrisense_verify")
WA_APP_SECRET = env("WA_APP_SECRET")  # empty = skip signature check (dev only)
WA_API_VERSION = env("WA_API_VERSION", "v25.0")
# "cloud" = real WhatsApp via Meta. "web" = the browser chat at /chat/ (no Meta account needed).
# Defaults to "web" until a WhatsApp access token is configured.
WA_TRANSPORT = env("WA_TRANSPORT") or ("cloud" if WA_ACCESS_TOKEN else "web")
# Process webhooks in a background thread so Meta gets its 200 fast.
WA_ASYNC = env_bool("WA_ASYNC", True)
# Minutes of silence after which a half-finished flow resets to the main menu.
WA_SESSION_TIMEOUT_MIN = int(env("WA_SESSION_TIMEOUT_MIN", "30"))
# Template used for "did the treatment work?" follow-ups (must be approved in Meta).
WA_FOLLOWUP_TEMPLATE = env("WA_FOLLOWUP_TEMPLATE", "treatment_followup")
WA_FOLLOWUP_TEMPLATE_LANG = env("WA_FOLLOWUP_TEMPLATE_LANG", "en")

# --- crop.health (Kindwise) ----------------------------------------------
CROP_HEALTH_API_KEY = env("CROP_HEALTH_API_KEY")  # empty = demo/stub diagnosis
CROP_HEALTH_URL = env("CROP_HEALTH_URL", "https://crop.kindwise.com/api/v1/identification")
# Below this confidence the diagnosis is sent to an agrovet for confirmation.
DIAGNOSIS_REVIEW_THRESHOLD = float(env("DIAGNOSIS_REVIEW_THRESHOLD", "0.5"))

# --- Label check (OCR.space) ---------------------------------------------
# Free key at https://ocr.space/ocrapi/freekey. Empty = farmers type the PCPB number instead.
OCRSPACE_API_KEY = env("OCRSPACE_API_KEY")
REWARD_POINTS_VERIFIED_PURCHASE = int(env("REWARD_POINTS_VERIFIED_PURCHASE", "10"))

# --- M-Pesa Daraja -------------------------------------------------------
MPESA_ENV = env("MPESA_ENV", "sandbox")  # sandbox | production
MPESA_CONSUMER_KEY = env("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = env("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = env("MPESA_SHORTCODE", "174379")
MPESA_PASSKEY = env("MPESA_PASSKEY")
MPESA_TRANSACTION_TYPE = env("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline")
# Public base URL of this server, e.g. https://agrisense-bot.onrender.com
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
# Secret path segment so random callers can't fake payment callbacks.
MPESA_CALLBACK_TOKEN = env("MPESA_CALLBACK_TOKEN", "change-me")
