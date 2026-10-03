from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import DiagnosisProvider


def get_provider() -> DiagnosisProvider:
    """Build the configured diagnosis provider from settings.DIAGNOSIS."""
    config = settings.DIAGNOSIS
    name = config["PROVIDER"]
    if name == "kindwise":
        from .kindwise import KindwiseProvider

        return KindwiseProvider(
            api_key=config["KINDWISE_API_KEY"],
            base_url=config["KINDWISE_BASE_URL"],
            timeout=config["KINDWISE_TIMEOUT"],
            language=config["KINDWISE_LANGUAGE"],
            similar_images=config["KINDWISE_SIMILAR_IMAGES"],
        )
    raise ImproperlyConfigured(f"Unknown DIAGNOSIS_PROVIDER: {name!r}")
