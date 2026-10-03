import io
from unittest import mock

import numpy as np
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmerProfile, User


def image_bytes(pixels: np.ndarray, fmt="JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(pixels.astype(np.uint8)).save(buffer, format=fmt, quality=95)
    return buffer.getvalue()


def sharp_pixels(size=(600, 800), low=0, high=255, seed=1):
    """Random texture: lots of edges, like a focused photo of foliage."""
    return np.random.default_rng(seed).integers(low, high, size=(*size, 3))


def blurry_pixels(size=(600, 800)):
    """Smooth gradient: no edges at all, like an out-of-focus photo."""
    row = np.linspace(60, 200, size[1])
    grey = np.tile(row, (size[0], 1))
    return np.stack([grey] * 3, axis=-1)


def upload(content: bytes, name="photo.jpg"):
    return SimpleUploadedFile(name, content, content_type="image/jpeg")


@pytest.fixture
def sharp_photo():
    return lambda: upload(image_bytes(sharp_pixels()))


@pytest.fixture
def blurry_photo():
    return lambda: upload(image_bytes(blurry_pixels()))


def make_farmer(phone, language=FarmerProfile.Language.ENGLISH, ward="Chuka"):
    user = User.objects.create_user(username=phone, password="1234", phone=phone, first_name="Wanjiru")
    FarmerProfile.objects.create(
        user=user, language=language, county="Tharaka Nithi", ward=ward, consent_at=timezone.now()
    )
    return user


@pytest.fixture
def farmer(db):
    return make_farmer("+254700000001")


@pytest.fixture
def other_farmer(db):
    return make_farmer("+254700000002")


@pytest.fixture
def agrovet(db):
    return User.objects.create_user(username="agrovet1", password="x", role=User.Role.AGROVET)


@pytest.fixture
def farm(farmer):
    return Farm.objects.create(farmer=farmer, latitude="-0.330000", longitude="37.650000", size_acres="0.50")


@pytest.fixture
def api(farmer):
    api = APIClient()
    api.force_authenticate(farmer)
    return api


@pytest.fixture(autouse=True)
def task_delay():
    with mock.patch("apps.diagnosis.tasks.run_ai_diagnosis_task.delay") as delay:
        yield delay


VALID_ANSWERS = {
    "started": "3_to_7_days",
    "share_affected": "some",
    "recent_weather": ["rainy", "humid"],
    "already_sprayed": True,
    "sprayed_product": "Unknown blue bottle",
}
