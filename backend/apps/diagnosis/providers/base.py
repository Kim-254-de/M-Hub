"""Provider-agnostic contract for external image-diagnosis services.

The rest of the Diagnose module depends only on these types, so the
provider (Kindwise today) can be swapped without touching models or views.
"""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ImageInput:
    filename: str
    content: bytes
    content_type: str = "image/jpeg"


@dataclass(frozen=True)
class Suggestion:
    external_id: str
    name: str
    scientific_name: str
    probability: Decimal
    is_healthy: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    similar_images: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IdentificationResult:
    provider: str
    external_ref: str
    model_version: str
    is_plant_probability: Decimal | None
    crop_suggestions: list[Suggestion]
    disease_suggestions: list[Suggestion]
    raw: dict[str, Any]


class ProviderError(Exception):
    """Base class. ``code`` is a stable machine-readable reason stored on the record."""

    code = "provider_error"
    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderTemporaryError(ProviderError):
    """Timeouts, connection failures, 5xx: safe to retry with backoff."""

    code = "provider_unavailable"
    retryable = True


class ProviderAuthError(ProviderError):
    """Invalid or inactive API key. Needs operator action, not a retry."""

    code = "provider_auth"


class ProviderQuotaError(ProviderError):
    """Out of credits or over the key's limit. Needs operator action."""

    code = "provider_quota"


class ProviderRequestError(ProviderError):
    """The provider rejected our input (bad image, invalid field)."""

    code = "provider_rejected_request"


class ProviderResponseError(ProviderError):
    """The provider answered 2xx but the body is not what the contract says."""

    code = "provider_bad_response"
    retryable = True


class DiagnosisProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def identify(
        self,
        images: list[ImageInput],
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        taken_at: dt.datetime | None = None,
    ) -> IdentificationResult:
        """Identify crop and disease from one or more photos of the same plant."""
