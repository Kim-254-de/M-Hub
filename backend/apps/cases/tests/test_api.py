import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmerProfile
from apps.cases.models import Case, CasePhoto
from apps.diagnosis.models import AIDiagnosis

from .conftest import VALID_ANSWERS, make_farmer

pytestmark = pytest.mark.django_db

PHOTO_TYPES = ("leaf", "plant", "stem_fruit")


def cases_url():
    return reverse("v1:case-list")


def case_url(case, action=None):
    if action is None:
        return reverse("v1:case-detail", kwargs={"pk": case.id})
    return reverse(f"v1:case-{action}", kwargs={"pk": case.id})


def start(api, **data):
    response = api.post(cases_url(), data, format="json")
    assert response.status_code == 201, response.data
    return Case.objects.get(pk=response.data["id"])


def add_photo(api, case, photo_type, file):
    return api.post(case_url(case, "photos"), {"type": photo_type, "image": file}, format="multipart")


def ready_case(api, sharp_photo, **data):
    case = start(api, **data)
    for photo_type in PHOTO_TYPES:
        assert add_photo(api, case, photo_type, sharp_photo()).status_code == 201
    assert api.put(case_url(case, "answers"), VALID_ANSWERS, format="json").status_code == 200
    return case


# --- Access -----------------------------------------------------------------


def test_requires_authentication():
    assert APIClient().get(cases_url()).status_code == 401


def test_agrovet_cannot_report(agrovet):
    api = APIClient()
    api.force_authenticate(agrovet)
    assert api.post(cases_url(), {}, format="json").status_code == 403


def test_farmer_sees_only_own_cases(api, other_farmer):
    mine = start(api)
    theirs = Case.objects.create(farmer=other_farmer, status=Case.Status.DRAFT)

    listed = [c["id"] for c in api.get(cases_url()).data]
    assert listed == [str(mine.id)]
    assert api.get(case_url(theirs)).status_code == 404
    assert api.put(case_url(theirs, "answers"), VALID_ANSWERS, format="json").status_code == 404


# --- Start ------------------------------------------------------------------


def test_start_creates_draft(api, farm):
    response = api.post(cases_url(), {"farm": str(farm.id)}, format="json")

    assert response.status_code == 201
    assert response.data["status"] == "DRAFT"
    assert response.data["missing_photos"] == list(PHOTO_TYPES)
    assert response.data["detection"] == {
        "ai_status": None,
        "needs_retake": False,
        "retake_reason": None,
        "retake_message": None,
    }


def test_cannot_use_another_farmers_farm(api, other_farmer):
    farm = Farm.objects.create(farmer=other_farmer, latitude=0, longitude=37, size_acres=1)
    assert api.post(cases_url(), {"farm": str(farm.id)}, format="json").status_code == 400


def test_latitude_requires_longitude(api):
    assert api.post(cases_url(), {"latitude": "-0.3"}, format="json").status_code == 400


# --- Photos -----------------------------------------------------------------


def test_upload_photo(api, sharp_photo):
    case = start(api)
    response = add_photo(api, case, "leaf", sharp_photo())

    assert response.status_code == 201
    assert response.data["type"] == "leaf"
    photo = case.photos.get()
    assert (photo.width, photo.height) == (800, 600)
    assert photo.sharpness > 0


def test_new_photo_replaces_same_type(api, sharp_photo):
    case = start(api)
    first = add_photo(api, case, "leaf", sharp_photo()).data["id"]
    second = add_photo(api, case, "leaf", sharp_photo()).data["id"]

    assert str(case.photos.get().id) == second
    assert not CasePhoto.objects.filter(pk=first).exists()


def test_blurry_photo_asks_for_retake_in_farmers_language(api, farmer, blurry_photo):
    FarmerProfile.objects.filter(user=farmer).update(language="sw")
    case = start(api)

    response = add_photo(api, case, "leaf", blurry_photo())

    assert response.status_code == 422
    assert response.data["code"] == "blurry"
    assert "haiko wazi" in response.data["detail"]
    assert not case.photos.exists()


def test_label_type_not_accepted_in_detect(api, sharp_photo):
    case = start(api)
    assert add_photo(api, case, "label", sharp_photo()).status_code == 400


# --- Answers ----------------------------------------------------------------


def test_save_answers(api):
    case = start(api)
    response = api.put(case_url(case, "answers"), VALID_ANSWERS, format="json")

    assert response.status_code == 200
    case.refresh_from_db()
    assert case.symptom_answers["recent_weather"] == ["humid", "rainy"]
    assert case.symptom_answers["share_affected"] == "some"


@pytest.mark.parametrize(
    "change",
    [{"started": "yesterday"}, {"share_affected": None}, {"recent_weather": []}, {"already_sprayed": None}],
)
def test_invalid_answers_rejected(api, change):
    case = start(api)
    answers = {**VALID_ANSWERS, **change}
    assert api.put(case_url(case, "answers"), answers, format="json").status_code == 400


# --- Submit -----------------------------------------------------------------


def test_submit_reports_case_and_queues_ai(
    api, farm, sharp_photo, task_delay, django_capture_on_commit_callbacks
):
    case = ready_case(api, sharp_photo, farm=str(farm.id))

    with django_capture_on_commit_callbacks(execute=True):
        response = api.post(case_url(case, "submit"))

    assert response.status_code == 202
    assert response.data["status"] == "REPORTED"
    assert response.data["detection"]["ai_status"] == "PENDING"
    case.refresh_from_db()
    assert case.submitted_at is not None
    # Location falls back to the farm, area comes from the farmer's profile.
    assert (str(case.latitude), str(case.longitude)) == ("-0.330000", "37.650000")
    assert (case.county, case.ward) == ("Tharaka Nithi", "Chuka")
    ai = AIDiagnosis.objects.get(case=case)
    task_delay.assert_called_once_with(str(ai.id))


def test_photo_gps_takes_priority_over_farm(api, farm, sharp_photo):
    case = ready_case(api, sharp_photo, farm=str(farm.id), latitude="-0.300000", longitude="37.600000")
    api.post(case_url(case, "submit"))
    case.refresh_from_db()
    assert str(case.latitude) == "-0.300000"


def test_submit_requires_all_photos(api, sharp_photo):
    case = start(api)
    add_photo(api, case, "leaf", sharp_photo())
    api.put(case_url(case, "answers"), VALID_ANSWERS, format="json")

    response = api.post(case_url(case, "submit"))

    assert response.status_code == 400
    assert response.data["code"] == "case_incomplete"
    assert "plant" in response.data["detail"]
    case.refresh_from_db()
    assert case.status == Case.Status.DRAFT
    assert not AIDiagnosis.objects.exists()


def test_submit_requires_answers(api, sharp_photo):
    case = start(api)
    for photo_type in PHOTO_TYPES:
        add_photo(api, case, photo_type, sharp_photo())
    assert api.post(case_url(case, "submit")).status_code == 400


def test_submitted_case_is_locked(api, sharp_photo):
    case = ready_case(api, sharp_photo)
    api.post(case_url(case, "submit"))

    assert add_photo(api, case, "leaf", sharp_photo()).status_code == 409
    assert api.put(case_url(case, "answers"), VALID_ANSWERS, format="json").status_code == 409
    assert api.post(case_url(case, "submit")).status_code == 409
    assert AIDiagnosis.objects.filter(case=case).count() == 1


# --- Retake after the AI check ----------------------------------------------


def finish_ai(case, **result):
    AIDiagnosis.objects.filter(case=case).update(status=AIDiagnosis.Status.COMPLETED, **result)


def test_not_tomato_lets_farmer_retake_and_resubmit(api, sharp_photo):
    case = ready_case(api, sharp_photo)
    api.post(case_url(case, "submit"))
    first_submitted_at = Case.objects.get(pk=case.pk).submitted_at
    finish_ai(case, is_plant=True, is_tomato=False)

    detection = api.get(case_url(case)).data["detection"]
    assert detection["needs_retake"] is True
    assert detection["retake_reason"] == "not_tomato"
    assert "tomato" in detection["retake_message"]

    assert add_photo(api, case, "plant", sharp_photo()).status_code == 201
    response = api.post(case_url(case, "submit"))

    assert response.status_code == 202
    assert AIDiagnosis.objects.filter(case=case).count() == 2
    assert response.data["detection"]["ai_status"] == "PENDING"
    assert Case.objects.get(pk=case.pk).submitted_at == first_submitted_at


def test_not_plant_reason(api, sharp_photo):
    case = ready_case(api, sharp_photo)
    api.post(case_url(case, "submit"))
    finish_ai(case, is_plant=False, is_tomato=None)

    assert api.get(case_url(case)).data["detection"]["retake_reason"] == "not_plant"


def test_good_ai_result_keeps_case_locked(api, sharp_photo):
    case = ready_case(api, sharp_photo)
    api.post(case_url(case, "submit"))
    finish_ai(case, is_plant=True, is_tomato=True)
    Case.objects.filter(pk=case.pk).update(status=Case.Status.DIAGNOSING)

    assert api.get(case_url(case)).data["detection"]["needs_retake"] is False
    assert add_photo(api, case, "leaf", sharp_photo()).status_code == 409


def test_farmer_without_profile_gets_english_messages(db, blurry_photo):
    farmer = make_farmer("+254711111111")
    FarmerProfile.objects.filter(user=farmer).delete()
    api = APIClient()
    api.force_authenticate(farmer)
    case = start(api)

    response = add_photo(api, case, "leaf", blurry_photo())

    assert response.status_code == 422
    assert response.data["detail"].startswith("This photo is blurry")
