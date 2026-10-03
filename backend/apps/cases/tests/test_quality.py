import io

import pytest
from django.test import override_settings

from apps.cases.quality import PhotoQualityError, assess_photo

from .conftest import blurry_pixels, image_bytes, sharp_pixels


def check(pixels, fmt="JPEG"):
    return assess_photo(io.BytesIO(image_bytes(pixels, fmt)))


def test_sharp_photo_passes_and_is_measured():
    quality = check(sharp_pixels())
    assert (quality.width, quality.height) == (800, 600)
    assert quality.sharpness > 1000
    assert 100 < quality.brightness < 160


def test_blurry_photo_rejected():
    with pytest.raises(PhotoQualityError) as exc:
        check(blurry_pixels())
    assert exc.value.reason == "blurry"


def test_dark_photo_rejected():
    with pytest.raises(PhotoQualityError) as exc:
        check(sharp_pixels(low=0, high=30))
    assert exc.value.reason == "too_dark"


def test_small_photo_rejected():
    with pytest.raises(PhotoQualityError) as exc:
        check(sharp_pixels(size=(300, 400)))
    assert exc.value.reason == "too_small"


def test_non_image_rejected():
    with pytest.raises(PhotoQualityError) as exc:
        assess_photo(io.BytesIO(b"not an image"))
    assert exc.value.reason == "invalid_image"


def test_png_supported():
    assert check(sharp_pixels(), fmt="PNG").width == 800


def test_file_is_rewound_for_saving():
    fh = io.BytesIO(image_bytes(sharp_pixels()))
    assess_photo(fh)
    assert fh.tell() == 0


def test_thresholds_come_from_settings():
    with override_settings(DETECT={**_detect(), "MIN_SHARPNESS": 1e9}):
        with pytest.raises(PhotoQualityError):
            check(sharp_pixels())


def _detect():
    from django.conf import settings

    return settings.DETECT
