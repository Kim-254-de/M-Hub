"""OCR.space client for reading product labels. Docs: https://ocr.space/ocrapi"""

from __future__ import annotations

import io
import logging

import requests
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2000


class OcrError(Exception):
    retryable = False


class OcrConfigError(OcrError):
    pass


class OcrTemporaryError(OcrError):
    retryable = True


class OcrImageError(OcrError):
    """The uploaded file is not a readable image."""


def prepare_image(content: bytes, *, max_bytes: int) -> bytes:
    """Upright, RGB JPEG under ``max_bytes`` (OCR.space free tier rejects files over 1 MB)."""
    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise OcrImageError("The photo could not be read as an image.") from exc

    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    for quality in (90, 80, 70, 60, 50):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= max_bytes:
            return buffer.getvalue()
        # Shrink as well as recompress: label text stays legible well below 2000px.
        img.thumbnail((int(img.width * 0.8), int(img.height * 0.8)))
    raise OcrImageError("The photo is too large to process. Please retake it closer to the label.")


class OcrSpaceClient:
    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        engine: int,
        timeout: tuple[float, float],
        max_upload_bytes: int,
        session: requests.Session | None = None,
    ):
        if not api_key:
            raise OcrConfigError("OCRSPACE_API_KEY is not configured")
        self._api_key = api_key
        self._url = url
        self._engine = engine
        self._timeout = timeout
        self._max_upload_bytes = max_upload_bytes
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls) -> OcrSpaceClient:
        config = settings.OCR
        return cls(
            api_key=config["OCRSPACE_API_KEY"],
            url=config["OCRSPACE_URL"],
            engine=config["OCRSPACE_ENGINE"],
            timeout=config["TIMEOUT"],
            max_upload_bytes=config["MAX_UPLOAD_BYTES"],
        )

    def read_text(self, content: bytes) -> str:
        """Return all text found in the image (may be empty)."""
        image = prepare_image(content, max_bytes=self._max_upload_bytes)
        try:
            response = self._session.post(
                self._url,
                headers={"apikey": self._api_key},
                files={"file": ("label.jpg", image, "image/jpeg")},
                data={
                    "language": "eng",
                    "OCREngine": str(self._engine),
                    "scale": "true",
                    "detectOrientation": "true",
                    "isOverlayRequired": "false",
                    "filetype": "JPG",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise OcrTemporaryError(f"OCR request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise OcrConfigError(f"OCR.space rejected the API key (HTTP {response.status_code})")
        if response.status_code == 429 or response.status_code >= 500:
            raise OcrTemporaryError(f"OCR.space HTTP {response.status_code}")
        if response.status_code != 200:
            raise OcrError(f"OCR.space HTTP {response.status_code}: {response.text[:200]}")

        try:
            data = response.json()
        except ValueError as exc:
            # OCR.space returns plain text for some errors (e.g. invalid key, rate limit).
            text = response.text[:200]
            if "api key" in text.lower():
                raise OcrConfigError(f"OCR.space: {text}") from exc
            raise OcrTemporaryError(f"OCR.space returned a non-JSON body: {text}") from exc

        if data.get("IsErroredOnProcessing"):
            message = data.get("ErrorMessage")
            message = "; ".join(message) if isinstance(message, list) else str(message)
            # Exit code 3/4 with a timeout message is transient; anything else is about the input.
            if "timed out" in message.lower() or "timeout" in message.lower():
                raise OcrTemporaryError(f"OCR.space: {message}")
            raise OcrError(f"OCR.space: {message}")

        results = data.get("ParsedResults") or []
        return "\n".join(r.get("ParsedText", "") for r in results if r.get("FileParseExitCode") == 1).strip()
