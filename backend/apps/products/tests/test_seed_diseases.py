import pytest
from django.core.management import call_command

from apps.products.models import Disease

pytestmark = pytest.mark.django_db


def test_seed_adds_late_and_early_blight_once():
    call_command("seed_diseases")
    call_command("seed_diseases")
    assert sorted(Disease.objects.values_list("name", flat=True)) == ["Early blight", "Late blight"]
    late = Disease.objects.get(name="Late blight")
    assert late.local_names["sw"] == "Baa chelewa" and late.safe_actions["en"]


def test_seed_keeps_admin_edits_and_fills_gaps():
    Disease.objects.create(name="late blight", local_names={"sw": "Edited"})
    call_command("seed_diseases")
    late = Disease.objects.get(name__iexact="late blight")
    assert late.local_names == {"sw": "Edited"}
    assert late.scientific_name == "Phytophthora infestans"
