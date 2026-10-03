from django.conf import settings

from .base import Provider, ProviderError, Reply

__all__ = ["Provider", "ProviderError", "Reply", "get_provider"]


def get_provider(name: str | None = None, **kwargs) -> Provider:
    name = name or settings.ADVISORY["PROVIDER"]
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(**kwargs)
    if name == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(**kwargs)
    raise ValueError(f"Unknown advisory provider: {name}")
