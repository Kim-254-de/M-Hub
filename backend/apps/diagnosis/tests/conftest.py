import copy
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import User
from apps.cases.models import Case, CasePhoto

KINDWISE_URL = "https://kindwise.test/api/v1/identification"

# Shape taken from the official crop.health documentation examples.
KINDWISE_RESPONSE = {
    "access_token": "SChIQy84K8bvPtd",
    "model_version": "crop_health:1.1.1",
    "custom_id": None,
    "input": {"latitude": -0.33, "longitude": 37.65, "similar_images": True, "images": ["https://x/1.jpg"]},
    "result": {
        "is_plant": {"probability": 1, "threshold": 0.5, "binary": True},
        "disease": {
            "suggestions": [
                {
                    "id": "c35556c0c67c0591",
                    "name": "healthy",
                    "probability": 0.0103,
                    "similar_images": [],
                    "details": {"language": "en", "entity_id": "c35556c0c67c0591"},
                    "scientific_name": "healthy",
                },
                {
                    "id": "b9ec757fefb92520",
                    "name": "late blight",
                    "probability": 0.9806,
                    "similar_images": [
                        {
                            "id": "100ac657",
                            "url": "https://cdn.test/1.jpg",
                            "license_name": "CC BY 3.0",
                            "citation": "Howard F. Schwartz, Colorado State University",
                            "similarity": 0.789,
                        }
                    ],
                    "details": {
                        "language": "en",
                        "entity_id": "b9ec757fefb92520",
                        "common_names": ["Late Blight Of Tomato"],
                        "type": "chromista",
                        "description": "Late blight is a destructive plant disease.",
                        "symptoms": {"Leaf discoloration": "Greenish-black spots."},
                        "severity": "Severe.",
                        "spreading": "Airborne spores.",
                        "treatment": {
                            "prevention": ["Regular field monitoring."],
                            "chemical treatment": ["Apply Ridomil Gold."],
                            "biological treatment": ["Apply Serenade."],
                        },
                        "wiki_url": "https://en.wikipedia.org/wiki/Phytophthora_infestans",
                        "eppo_code": "PHYTIN",
                    },
                    "scientific_name": "Phytophthora infestans",
                },
                {
                    "id": "a1",
                    "name": "early blight",
                    "probability": 0.004,
                    "details": {},
                    "scientific_name": "Alternaria solani",
                },
                {
                    "id": "a2",
                    "name": "septoria leaf spot",
                    "probability": 0.002,
                    "details": {},
                    "scientific_name": "Septoria lycopersici",
                },
            ]
        },
        "crop": {
            "suggestions": [
                {
                    "id": "t1",
                    "name": "tomato",
                    "probability": 0.91,
                    "scientific_name": "Solanum lycopersicum",
                },
                {"id": "p1", "name": "potato", "probability": 0.05, "scientific_name": "Solanum tuberosum"},
            ]
        },
    },
    "status": "COMPLETED",
    "sla_compliant_client": True,
    "sla_compliant_system": True,
    "created": 1710322935.948778,
    "completed": 1710322936.674678,
}


@pytest.fixture
def kindwise_response():
    return copy.deepcopy(KINDWISE_RESPONSE)


def make_image_bytes(size=(64, 64), fmt="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 120, 40)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def farmer(db):
    return User.objects.create_user(username="farmer1", password="x", phone="+254700000001")


@pytest.fixture
def other_farmer(db):
    return User.objects.create_user(username="farmer2", password="x", phone="+254700000002")


@pytest.fixture
def staff(db):
    return User.objects.create_user(username="admin1", password="x", is_staff=True, role=User.Role.ADMIN)


@pytest.fixture
def case(farmer):
    return Case.objects.create(farmer=farmer, latitude="-0.330000", longitude="37.650000")


@pytest.fixture
def case_with_photos(case):
    for photo_type in (CasePhoto.Type.LEAF, CasePhoto.Type.PLANT, CasePhoto.Type.STEM_FRUIT):
        CasePhoto.objects.create(
            case=case,
            type=photo_type,
            image=SimpleUploadedFile(f"{photo_type}.jpg", make_image_bytes(), content_type="image/jpeg"),
        )
    return case
