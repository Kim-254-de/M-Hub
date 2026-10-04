from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

WHATSAPP = {
    **WHATSAPP,  # noqa: F405
    "TRANSPORT": env("WHATSAPP_TRANSPORT", default="web"),
    "SIMULATOR_ENABLED": env.bool("WHATSAPP_SIMULATOR_ENABLED", default=True),
}
