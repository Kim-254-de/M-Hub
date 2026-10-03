from __future__ import annotations

from dataclasses import dataclass, field


class ProviderError(Exception):
    """The model could not be reached or failed. ``retryable`` for rate limits and server errors."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Reply:
    text: str
    model: str  # as reported by the response, not as requested
    stop_reason: str
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    fell_back: bool = False  # another model answered after the requested one declined


class Provider:
    name = "base"

    def reply(self, *, system: str, user: str, model: str, allow_fallback: bool = True) -> Reply:
        raise NotImplementedError
