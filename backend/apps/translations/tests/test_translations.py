"""Reviewed translations: Kikuyu text reaches farmers only once approved and while still current."""

import csv
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.accounts.models import User
from apps.diagnosis.messages import general_safe_actions, safe_actions, status_message
from apps.followups.messages import advice
from apps.notifications.messages import farmer_message
from apps.prescriptions.messages import card_instructions, sms_quantity
from apps.prescriptions.models import Prescription
from apps.products.models import Disease, Product
from apps.translations import catalog
from apps.translations.models import Translation

pytestmark = pytest.mark.django_db

# Stand-ins, not Kikuyu: real Kikuyu text comes from a human translator.
KI = "[ki] "


@pytest.fixture
def reviewer(db):
    return User.objects.create_user(username="reviewer", password="x")


def translate(key, text, *, reviewer=None, language="ki"):
    translation = Translation.objects.create(
        key=key, language=language, text=text, source_text=catalog.get_source(key).english
    )
    if reviewer is not None:
        translation.approve(reviewer)
    return translation


def test_code_text_is_valid_for_every_message():
    """English and Kiswahili in code pass the same checks a translation must pass."""
    for source in catalog.sources():
        for language, text in source.texts.items():
            assert source.problems(text) == [], (source.key, language)


def test_kikuyu_without_reviewed_text_falls_back_to_kiswahili():
    assert advice("complete", "ki") == advice("complete", "sw")
    assert general_safe_actions("ki") == general_safe_actions("sw")


def test_only_approved_current_translations_are_shown(reviewer):
    draft = translate("followups.advice.complete", KI + "draft")
    assert advice("complete", "ki") == advice("complete", "sw")

    draft.approve(reviewer)
    assert advice("complete", "ki") == KI + "draft"
    assert advice("complete", "sw") != KI + "draft"


def test_translation_of_old_english_is_not_shown(reviewer):
    translation = translate("followups.advice.complete", KI + "thanks", reviewer=reviewer)
    Translation.objects.filter(pk=translation.pk).update(source_checksum=catalog.checksum("Old English."))

    assert advice("complete", "ki") == advice("complete", "sw")
    translation.refresh_from_db()
    assert not translation.is_current
    with pytest.raises(ValidationError):
        translation.approve(reviewer)


def test_editing_an_approved_translation_needs_a_new_review(reviewer):
    translation = translate("followups.advice.complete", KI + "thanks", reviewer=reviewer)
    translation.text = KI + "thank you"
    translation.save()

    assert translation.status == Translation.Status.DRAFT and translation.reviewed_by is None
    assert advice("complete", "ki") == advice("complete", "sw")


def test_a_screen_never_mixes_languages(reviewer):
    translate("diagnosis.safe_actions.0", KI + "remove spotted leaves", reviewer=reviewer)
    # Only one of five steps is translated: all five stay in Kiswahili.
    assert general_safe_actions("ki") == general_safe_actions("sw")


def test_placeholders_must_match_the_english(reviewer):
    translation = translate("followups.advice.stopped", KI + "day {siku}")
    assert "Placeholders" in " ".join(translation.problems())
    with pytest.raises(ValidationError):
        translation.approve(reviewer)

    translation.text = KI + "day {next_day}"
    translation.save()
    translation.approve(reviewer)
    assert advice("stopped", "ki", next_day=4) == KI + "day 4"


def test_sms_translations_keep_to_gsm_and_the_length_limit(reviewer):
    key = "sms.farmer.received"
    assert translate(key, "Nĩ ũhoro mwega").problems() == []  # tilde vowels are sent without the tilde
    Translation.objects.all().delete()
    assert "GSM-7" in " ".join(translate(key, "Habari ☺").problems())
    Translation.objects.all().delete()
    assert "limit is 160" in " ".join(translate(key, "a" * 161).problems())

    Translation.objects.all().delete()
    translate(key, "AgriSense: Nĩ ũhoro.", reviewer=reviewer)
    assert farmer_message("received", "ki") == "AgriSense: Ni uhoro."


def test_disease_names_and_steps_fall_back_to_kiswahili():
    disease = Disease(
        name="Late blight",
        local_names={"sw": "Baa chelewa"},
        safe_actions={"sw": ["Ondoa majani yenye madoa."]},
    )
    assert disease.display_name("ki") == "Baa chelewa"
    assert safe_actions(disease, "ki") == ["Ondoa majani yenye madoa."]

    disease.local_names["ki"] = "Mbutu"
    assert disease.display_name("ki") == "Mbutu"
    assert status_message("DIAGNOSED", "ki", disease="Mbutu").endswith("Mbutu.")


def test_reviewed_general_steps_beat_disease_steps_in_another_language(reviewer):
    for i in range(len(general_safe_actions("en"))):
        translate(f"diagnosis.safe_actions.{i}", f"{KI}step {i}", reviewer=reviewer)
    disease = Disease(name="Late blight", safe_actions={"sw": ["Ondoa majani yenye madoa."]})

    assert safe_actions(disease, "ki")[0] == KI + "step 0"


def _prescription(**dose):
    product = Product(
        pcpb_reg_no="PCPB (CR) 0856",
        name="Ridomil",
        label_rate="50 g per 20 L",
        phi_days=7,
        ppe_notes="Toxic.",
    )
    return Prescription(approved_product=product, **dose)


def test_card_instructions_are_templated_from_numbers():
    prescription = _prescription(
        dose_amount=Decimal("125"), dose_unit="g", dose_packs=1, dose_pack_size=Decimal("250")
    )
    en = card_instructions(prescription, "en")
    assert en["dose"] == "Buy 1 x 250 g. Mix 125 g for one spray of your farm."
    assert en["harvest"] == "Do not harvest for 7 days after spraying."
    assert en["label_notes"] == "Toxic."
    assert len(en["safety"]) == 6

    sw = card_instructions(prescription, "sw")
    assert sw["language"] == "sw" and sw["dose"].startswith("Nunua 1 x 250 g.")
    assert card_instructions(prescription, "ki") == sw | {"language": "sw"}

    label_only = card_instructions(_prescription(), "en")
    assert label_only["dose"] == "Mix the amount written on the label: 50 g per 20 L."


def test_sms_quantity_is_numbers_or_the_label_in_the_farmers_language():
    assert (
        sms_quantity(_prescription(dose_packs=2, dose_pack_size=Decimal("250"), dose_unit="g")) == "2 x 250 g"
    )
    assert sms_quantity(_prescription(), "sw") == "tumia kiasi kilichoandikwa kwenye lebo"


def test_export_and_import_round_trip(tmp_path, reviewer):
    path = tmp_path / "ki.csv"
    call_command("export_translations", language="ki", output=str(path))
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["status"] for r in rows} == {"missing"}
    assert len(rows) == len(catalog.sources())

    by_key = {r["key"]: r for r in rows}
    by_key["followups.advice.stopped"]["translation"] = KI + "day {next_day}"
    by_key["followups.advice.fewer"]["translation"] = KI + "no placeholder"
    by_key["followups.advice.complete"]["translation"] = KI + "thanks"
    by_key["followups.advice.complete"]["english"] = "Changed since export."
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(by_key.values())

    call_command("import_translations", str(path), language="ki", translator="Translator A")

    [saved] = Translation.objects.all()
    assert (saved.key, saved.status, saved.translated_by) == (
        "followups.advice.stopped",
        Translation.Status.DRAFT,
        "Translator A",
    )
    assert advice("stopped", "ki", next_day=4) == advice("stopped", "sw", next_day=4)  # not yet reviewed
