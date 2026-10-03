"""Farmer-facing dose and safety text for the prescription card and SMS (Documentation §11).

Templated so the numbers come from the label and the farm, never from free text. English and
Kiswahili are written here; other languages are reviewed translations (apps.translations).
The product label's own safety notes are shown as printed.
"""

from decimal import ROUND_HALF_UP, Decimal

from apps.translations.catalog import register

CARD_MESSAGES = {
    "dose_packs": {
        "en": "Buy {packs} x {pack_size} {unit}. Mix {amount} {unit} for one spray of your farm.",
        "sw": "Nunua {packs} x {pack_size} {unit}. Changanya {amount} {unit} kwa kunyunyizia shamba lako "
        "mara moja.",
    },
    "dose_amount": {
        "en": "Mix {amount} {unit} for one spray of your farm.",
        "sw": "Changanya {amount} {unit} kwa kunyunyizia shamba lako mara moja.",
    },
    "dose_label": {
        "en": "Mix the amount written on the label: {label_rate}.",
        "sw": "Changanya kiasi kilichoandikwa kwenye lebo: {label_rate}.",
    },
    "dose_label_only": {
        "en": "Mix the amount written on the label.",
        "sw": "Changanya kiasi kilichoandikwa kwenye lebo.",
    },
    "harvest_wait": {
        "en": "Do not harvest for {phi_days} days after spraying.",
        "sw": "Usivune kwa siku {phi_days} baada ya kunyunyizia.",
    },
    "harvest_label": {
        "en": "Read the label for how many days to wait after spraying before you harvest.",
        "sw": "Soma lebo ujue siku za kusubiri baada ya kunyunyizia kabla ya kuvuna.",
    },
    "ppe_wear": {
        "en": "Wear gloves, a mask, boots and long sleeves when you mix and spray.",
        "sw": "Vaa glavu, barakoa, buti na nguo za mikono mirefu unapochanganya na kunyunyizia.",
    },
    "ppe_no_eating": {
        "en": "Do not eat, drink or smoke while you mix or spray.",
        "sw": "Usile, usinywe wala usivute sigara unapochanganya au kunyunyizia.",
    },
    "ppe_weather": {
        "en": "Do not spray in strong wind or when rain is coming.",
        "sw": "Usinyunyizie wakati wa upepo mkali au mvua inapokaribia kunyesha.",
    },
    "ppe_people": {
        "en": "Keep children and animals away from the spray and the field.",
        "sw": "Weka watoto na mifugo mbali na dawa na shamba.",
    },
    "ppe_water": {
        "en": "Do not wash the sprayer or throw the empty pack near a river, well or dam.",
        "sw": "Usioshe bomba la kunyunyizia wala kutupa pakiti tupu karibu na mto, kisima au bwawa.",
    },
    "ppe_wash": {
        "en": "After spraying, wash your body and clothes with soap and water.",
        "sw": "Baada ya kunyunyizia, osha mwili na nguo zako kwa sabuni na maji.",
    },
}
SAFETY_NAMES = ["ppe_wear", "ppe_no_eating", "ppe_weather", "ppe_people", "ppe_water", "ppe_wash"]

# The dose in the prescription SMS. Numbers need no translation; "follow the label" does.
SMS_QUANTITY = {
    "follow_label": {"en": "use the rate on the label", "sw": "tumia kiasi kilichoandikwa kwenye lebo"},
}

_card = register("prescriptions.card", CARD_MESSAGES, safety=True)
_sms = register(
    "prescriptions.sms_quantity", SMS_QUANTITY, sms=True, safety=True, max_lengths={"follow_label": 40}
)


def format_amount(value) -> str:
    value = Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{value.normalize():f}"


def _dose_name(prescription, label_rate: str) -> str:
    if prescription.dose_packs and prescription.dose_pack_size:
        return "dose_packs"
    if prescription.dose_amount:
        return "dose_amount"
    return "dose_label" if label_rate else "dose_label_only"


def card_instructions(prescription, language: str = "en") -> dict:
    """How much to mix, when it is safe to harvest, and how to spray safely, all in one language."""
    product = prescription.approved_product
    label_rate = product.label_rate if product else ""
    phi_days = product.phi_days if product else None
    dose = _dose_name(prescription, label_rate)
    harvest = "harvest_label" if phi_days is None else "harvest_wait"
    used, texts = _card.group([dose, harvest, *SAFETY_NAMES], language)
    values = {
        "packs": prescription.dose_packs,
        "pack_size": format_amount(prescription.dose_pack_size) if prescription.dose_pack_size else "",
        "amount": format_amount(prescription.dose_amount) if prescription.dose_amount else "",
        "unit": prescription.dose_unit,
        "label_rate": label_rate,
        "phi_days": phi_days,
    }
    return {
        "language": used,
        "dose": texts[dose].format(**values),
        "harvest": texts[harvest].format(**values),
        "safety": [texts[name] for name in SAFETY_NAMES],
        # As printed on the product label; not translated.
        "label_notes": product.ppe_notes if product else "",
    }


def sms_quantity(prescription, language: str = "en") -> str:
    """The prescribed amount, short enough for the SMS."""
    if prescription.dose_packs and prescription.dose_pack_size:
        pack = format_amount(prescription.dose_pack_size)
        return f"{prescription.dose_packs} x {pack} {prescription.dose_unit}"
    if prescription.dose_amount:
        return f"{format_amount(prescription.dose_amount)} {prescription.dose_unit}"
    return _sms.text("follow_label", language)
