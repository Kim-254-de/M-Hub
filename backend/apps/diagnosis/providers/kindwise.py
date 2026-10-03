"""Kindwise crop.health client.

API reference: https://crop.kindwise.com/docs
  POST {base}/identification   multipart images + latitude/longitude/datetime/similar_images
  Header: Api-Key
  401 invalid key, 429 out of credits, 201 identification result.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from .base import (
    DiagnosisProvider,
    IdentificationResult,
    ImageInput,
    ProviderAuthError,
    ProviderQuotaError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTemporaryError,
    Suggestion,
)

logger = logging.getLogger(__name__)

# Details we ask for. "treatment" is stored for audit and agrovet reference
# only; see serializers.SAFE_DETAIL_KEYS for what is exposed through the API.
DETAILS = (
    "common_names",
    "type",
    "description",
    "symptoms",
    "severity",
    "spreading",
    "treatment",
    "wiki_url",
    "eppo_code",
)

# Kindwise entity ids are stable while names may change; match on id first.
HEALTHY_ENTITY_IDS = frozenset({"c35556c0c67c0591"})


class KindwiseProvider(DiagnosisProvider):
    name = "kindwise"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: tuple[float, float],
        language: str = "en",
        similar_images: bool = True,
        session: requests.Session | None = None,
    ):
        if not api_key:
            raise ProviderAuthError("KINDWISE_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._language = language
        self._similar_images = similar_images
        self._session = session or requests.Session()

    def identify(
        self,
        images: list[ImageInput],
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        taken_at: dt.datetime | None = None,
    ) -> IdentificationResult:
        if not images:
            raise ProviderRequestError("At least one image is required")

        data: dict[str, str] = {"similar_images": "true" if self._similar_images else "false"}
        if latitude is not None and longitude is not None:
            data["latitude"] = str(latitude)
            data["longitude"] = str(longitude)
        if taken_at is not None:
            data["datetime"] = taken_at.isoformat()

        files = [
            (f"image{i}", (image.filename, image.content, image.content_type))
            for i, image in enumerate(images, start=1)
        ]
        params = {"details": ",".join(DETAILS), "language": self._language}

        try:
            response = self._session.post(
                f"{self._base_url}/identification",
                params=params,
                data=data,
                files=files,
                headers={"Api-Key": self._api_key},
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise ProviderTemporaryError(f"Kindwise request timed out: {exc}") from exc
        except requests.RequestException as exc:
            raise ProviderTemporaryError(f"Kindwise request failed: {exc}") from exc

        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                "Kindwise returned a non-JSON body", status_code=response.status_code
            ) from exc

        return self._parse(payload)

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        message = f"Kindwise HTTP {status}: {response.text[:300]}"
        if status == 401:
            raise ProviderAuthError(message, status_code=status)
        if status == 429:
            raise ProviderQuotaError(message, status_code=status)
        if status in (408, 425) or status >= 500:
            raise ProviderTemporaryError(message, status_code=status)
        raise ProviderRequestError(message, status_code=status)

    def _parse(self, payload: dict[str, Any]) -> IdentificationResult:
        try:
            result = payload["result"]
            access_token = payload["access_token"]
        except (KeyError, TypeError) as exc:
            # A 2xx without "result" means the identification did not complete synchronously.
            status = payload.get("status") if isinstance(payload, dict) else None
            raise ProviderResponseError(f"Kindwise response missing result (status={status})") from exc

        is_plant = result.get("is_plant") or {}
        return IdentificationResult(
            provider=self.name,
            external_ref=str(access_token),
            model_version=str(payload.get("model_version", "")),
            is_plant_probability=_decimal(is_plant.get("probability")),
            crop_suggestions=_suggestions((result.get("crop") or {}).get("suggestions")),
            disease_suggestions=_suggestions((result.get("disease") or {}).get("suggestions")),
            raw=payload,
        )


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _suggestions(items: Any) -> list[Suggestion]:
    if not isinstance(items, list):
        return []
    parsed = []
    for item in items:
        probability = _decimal(item.get("probability"))
        if not item.get("id") or probability is None:
            logger.warning(
                "Skipping malformed Kindwise suggestion: %s", {k: item.get(k) for k in ("id", "name")}
            )
            continue
        details = dict(item.get("details") or {})
        details.pop("language", None)
        details.pop("entity_id", None)
        parsed.append(
            Suggestion(
                external_id=str(item["id"]),
                name=str(item.get("name") or ""),
                scientific_name=str(item.get("scientific_name") or ""),
                probability=probability,
                is_healthy=str(item["id"]) in HEALTHY_ENTITY_IDS
                or str(item.get("name", "")).lower() == "healthy",
                details=details,
                similar_images=list(item.get("similar_images") or []),
            )
        )
    parsed.sort(key=lambda s: s.probability, reverse=True)
    return parsed
