import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmerProfile, User
from apps.accounts.phone import normalize_kenyan_phone

pytestmark = pytest.mark.django_db

REGISTRATION = {
    "phone": "0712 345 678",
    "pin": "4821",
    "name": "Wanjiru Mwenda",
    "language": "sw",
    "county": "Tharaka Nithi",
    "ward": "Chuka",
    "consent": True,
}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0712345678", "+254712345678"),
        ("0112345678", "+254112345678"),
        ("254712345678", "+254712345678"),
        ("+254 712-345-678", "+254712345678"),
        ("712345678", "+254712345678"),
        ("0812345678", None),
        ("071234567", None),
        ("+255712345678", None),
        ("", None),
    ],
)
def test_normalize_kenyan_phone(raw, expected):
    assert normalize_kenyan_phone(raw) == expected


def register(data=None):
    return APIClient().post(reverse("v1:auth-register"), data or REGISTRATION, format="json")


def login(phone="0712345678", pin="4821"):
    return APIClient().post(reverse("v1:auth-token"), {"phone": phone, "pin": pin}, format="json")


def test_register_creates_farmer_and_returns_tokens():
    response = register()

    assert response.status_code == 201
    assert {"access", "refresh"} <= response.data.keys()
    user = User.objects.get(phone="+254712345678")
    assert user.role == User.Role.FARMER
    assert user.first_name == "Wanjiru Mwenda"
    assert user.check_password("4821")
    profile = user.farmer_profile
    assert (profile.language, profile.ward) == ("sw", "Chuka")
    assert profile.consent_at is not None


def test_register_requires_consent():
    response = register({**REGISTRATION, "consent": False})
    assert response.status_code == 400
    assert "consent" in response.data
    assert not User.objects.exists()


def test_register_rejects_duplicate_phone_in_any_format():
    register()
    response = register({**REGISTRATION, "phone": "+254712345678"})
    assert response.status_code == 400
    assert "phone" in response.data


@pytest.mark.parametrize("pin", ["123", "1234567", "12a4", ""])
def test_register_rejects_bad_pin(pin):
    assert register({**REGISTRATION, "pin": pin}).status_code == 400


def test_register_rejects_bad_phone():
    assert register({**REGISTRATION, "phone": "12345"}).status_code == 400


def test_login_with_any_phone_format():
    register()
    response = login(phone="+254 712 345 678")
    assert response.status_code == 200
    assert {"access", "refresh"} <= response.data.keys()


def test_login_wrong_pin():
    register()
    assert login(pin="0000").status_code == 401


def test_login_unknown_phone():
    assert login().status_code == 401


def test_login_inactive_user():
    register()
    User.objects.filter(phone="+254712345678").update(is_active=False)
    assert login().status_code == 401


def test_refresh_token():
    refresh = register().data["refresh"]
    response = APIClient().post(reverse("v1:auth-token-refresh"), {"refresh": refresh}, format="json")
    assert response.status_code == 200
    assert "access" in response.data


def test_auth_endpoints_are_throttled():
    statuses = [login(pin="0000").status_code for _ in range(11)]
    assert statuses[-1] == 429


# --- Farms --------------------------------------------------------------------


def bearer(access):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api


def test_farmer_manages_own_farms_with_jwt():
    api = bearer(register().data["access"])
    response = api.post(
        reverse("v1:farm-list"),
        {"name": "Shamba la juu", "latitude": "-0.330000", "longitude": "37.650000", "size_acres": "0.75"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["crops"] == ["tomato"]
    farm_id = response.data["id"]
    assert [f["id"] for f in api.get(reverse("v1:farm-list")).data] == [farm_id]

    updated = api.patch(
        reverse("v1:farm-detail", kwargs={"pk": farm_id}), {"size_acres": "1.00"}, format="json"
    )
    assert updated.status_code == 200
    assert updated.data["size_acres"] == "1.00"


def test_farm_validation():
    api = bearer(register().data["access"])
    bad = {"latitude": "95", "longitude": "37.65", "size_acres": "0"}
    response = api.post(reverse("v1:farm-list"), bad, format="json")
    assert response.status_code == 400
    assert {"latitude", "size_acres"} <= response.data.keys()


def test_farmer_cannot_see_other_farms():
    register()
    owner = User.objects.get(phone="+254712345678")
    farm = Farm.objects.create(farmer=owner, latitude=0, longitude=37, size_acres=1)
    other = register({**REGISTRATION, "phone": "0722000000"}).data["access"]

    assert bearer(other).get(reverse("v1:farm-detail", kwargs={"pk": farm.id})).status_code == 404


def test_agrovet_cannot_use_farm_endpoints():
    agrovet = User.objects.create_user(username="agro", password="x", role=User.Role.AGROVET)
    api = APIClient()
    api.force_authenticate(agrovet)
    assert api.get(reverse("v1:farm-list")).status_code == 403
    assert not FarmerProfile.objects.exists()
