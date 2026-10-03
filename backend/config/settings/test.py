import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from .base import *  # noqa: E402,F401,F403
from .base import DIAGNOSIS, MPESA, OCR  # noqa: E402

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
DIAGNOSIS = {
    **DIAGNOSIS,
    "KINDWISE_API_KEY": "test-api-key",
    "KINDWISE_BASE_URL": "https://kindwise.test/api/v1",
}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

MPESA = {
    **MPESA,
    "BASE_URL": "https://mpesa.test",
    "CONSUMER_KEY": "test-key",
    "CONSUMER_SECRET": "test-secret",
    "SHORTCODE": "174379",
    "PASSKEY": "test-passkey",
    "PARTY_B": "174379",
    "CALLBACK_BASE_URL": "https://api.agrisense.test",
    "CALLBACK_TOKEN": "test-callback-token",
}
OCR = {**OCR, "OCRSPACE_API_KEY": "test-ocr-key", "OCRSPACE_URL": "https://ocr.test/parse/image"}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
