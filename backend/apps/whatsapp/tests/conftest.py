import io
import os
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from PIL import Image

from apps.accounts.models import FarmerProfile, User
from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case
from apps.prescriptions.models import Prescription
from apps.products.models import Product
from apps.whatsapp.models import Conversation, OutboundMessage

PHONE = "+254712345678"


def sharp_photo(size=(900, 700)) -> bytes:
    """A noisy, bright photo that passes Detect's blur, darkness and size checks."""
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def no_ai_run():
    """Submitting a case queues the Kindwise run; not wanted in channel tests."""
    with mock.patch("apps.diagnosis.tasks.run_ai_diagnosis_task.delay") as delay:
        yield delay


@pytest.fixture
def chat(client, django_capture_on_commit_callbacks):
    """Send one farmer message through the simulator endpoint and return the replies it produced."""

    def send(phone=PHONE, **fields):
        before = set(OutboundMessage.objects.filter(phone=phone).values_list("id", flat=True))
        files = {}
        if "image" in fields:
            from django.core.files.uploadedfile import SimpleUploadedFile

            files["image"] = SimpleUploadedFile("photo.jpg", fields.pop("image"), content_type="image/jpeg")
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                "/whatsapp/simulator/api/send/", {"phone": phone, "name": "Peter Kamau", **fields, **files}
            )
        assert response.status_code == 200, response.content
        return [
            m.payload
            for m in OutboundMessage.objects.filter(phone=phone).exclude(id__in=before).order_by("created_at")
        ]

    return send


def body_of(payload) -> str:
    if payload["type"] == "text":
        return payload["text"]["body"]
    return payload["interactive"]["body"]["text"]


def ids_of(payload) -> list[str]:
    if payload["type"] != "interactive":
        return []
    action = payload["interactive"].get("action", {})
    ids = [b["reply"]["id"] for b in action.get("buttons", [])]
    ids += [r["id"] for s in action.get("sections", []) for r in s["rows"]]
    return ids


def all_text(payloads) -> str:
    return "\n".join(body_of(p) for p in payloads)


def register(chat):
    chat(text="Hi")
    chat(reply_id="REG_START")
    return chat(reply_id="REG_AGREE")


def choose_location(chat, county="Tharaka-Nithi", sub_county="Maara", ward="Chogoria"):
    chat(reply_id=f"LOC_C:{county}")
    chat(reply_id=f"LOC_S:{sub_county}")
    return chat(reply_id=f"LOC_W:{ward}")


@pytest.fixture
def farmer(db):
    user = User.objects.create_user(username=PHONE, phone=PHONE, first_name="Peter", role=User.Role.FARMER)
    FarmerProfile.objects.create(
        user=user,
        language="en",
        county="Tharaka-Nithi",
        sub_county="Maara",
        ward="Chogoria",
        consent_at=timezone.now(),
    )
    return user


@pytest.fixture
def on_whatsapp(farmer):
    """The farmer messaged the bot recently, so free-form WhatsApp messages are allowed."""
    return Conversation.objects.create(phone=PHONE, user=farmer, step="MENU", last_inbound_at=timezone.now())


@pytest.fixture
def agrovet(db):
    user = User.objects.create_user(username="agro1", password="x", role=User.Role.AGROVET)
    return Agrovet.objects.create(
        user=user,
        name="Chuka Agrovet",
        pcpb_licence_no="LIC-1",
        has_qualified_staff=True,
        phone="+254700111222",
        latitude="-0.330000",
        longitude="37.658000",
        status=Agrovet.Status.VERIFIED,
    )


@pytest.fixture
def product(db):
    return Product.objects.create(pcpb_reg_no="PCPB (CR) 0856", name="Ridomil Gold MZ 68 WG", phi_days=7)


@pytest.fixture
def store_item(agrovet, product):
    return StoreItem.objects.create(agrovet=agrovet, product=product, price_kes=650)


@pytest.fixture
def prescription(farmer, agrovet, product):
    case = Case.objects.create(
        farmer=farmer, status=Case.Status.PRESCRIBED, latitude="-0.333000", longitude="37.650000"
    )
    p = Prescription.objects.create(
        case=case,
        approved_product=product,
        quantity="1 x 250 g",
        approved_by=agrovet,
        expires_at=timezone.now() + timedelta(days=7),
    )
    p.allowed_products.set([product])
    return p
