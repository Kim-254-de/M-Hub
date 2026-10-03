"""Local photo quality checks run at upload (Documentation §6.1, step 3).

These are cheap and need no network, so a farmer is asked to retake a bad
photo immediately and no provider credit is spent on it. Whether the photo
shows a tomato plant is decided later by the AI run (``needs_retake``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError


class PhotoQualityError(Exception):
    """The photo must be retaken. ``reason`` is a stable code; see cases.messages."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class PhotoQuality:
    width: int
    height: int
    sharpness: float
    brightness: float


def assess_photo(fileobj) -> PhotoQuality:
    """Measure a photo and raise PhotoQualityError if it should be retaken."""
    config = settings.DETECT
    try:
        img = Image.open(fileobj)
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        img.draft("L", (config["ANALYSIS_SIZE"], config["ANALYSIS_SIZE"]))
        grey = img.convert("L")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoQualityError("invalid_image", str(exc)) from exc
    finally:
        if hasattr(fileobj, "seek"):
            fileobj.seek(0)

    if min(width, height) < config["MIN_PHOTO_SIDE"]:
        raise PhotoQualityError("too_small", f"{width}x{height}")

    # Measure on a fixed-size copy so the thresholds do not depend on camera resolution.
    grey.thumbnail((config["ANALYSIS_SIZE"], config["ANALYSIS_SIZE"]))
    pixels = np.asarray(grey, dtype=np.float64)
    brightness = float(pixels.mean())
    sharpness = _laplacian_variance(pixels)
    quality = PhotoQuality(width=width, height=height, sharpness=sharpness, brightness=brightness)

    if brightness < config["MIN_BRIGHTNESS"]:
        raise PhotoQualityError("too_dark", f"brightness={brightness:.1f}")
    if sharpness < config["MIN_SHARPNESS"]:
        raise PhotoQualityError("blurry", f"sharpness={sharpness:.1f}")
    return quality


def _laplacian_variance(pixels: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian: low when the image has few sharp edges."""
    laplacian = (
        pixels[:-2, 1:-1] + pixels[2:, 1:-1] + pixels[1:-1, :-2] + pixels[1:-1, 2:] - 4 * pixels[1:-1, 1:-1]
    )
    return float(laplacian.var())
