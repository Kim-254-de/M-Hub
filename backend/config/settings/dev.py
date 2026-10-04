from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# Expo web dev server (npm run web in mobile/)
CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS", default=["http://localhost:8081", "http://127.0.0.1:8081"]
)

WHATSAPP = {
    **WHATSAPP,  # noqa: F405
    "TRANSPORT": env("WHATSAPP_TRANSPORT", default="web"),
    "SIMULATOR_ENABLED": env.bool("WHATSAPP_SIMULATOR_ENABLED", default=True),
}
