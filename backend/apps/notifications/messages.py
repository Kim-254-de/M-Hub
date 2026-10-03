"""SMS texts by purpose and language.

Kept to plain GSM-7 characters so one SMS holds 160 characters (any other character
switches the whole message to UCS-2, where one SMS holds only 70). Never names a product
before a prescription is approved. English and Kiswahili are written here; other languages are
reviewed translations (apps.translations), checked against the same limits.
"""

from apps.translations.catalog import register
from apps.translations.gsm import to_gsm

__all__ = ["FARMER_MESSAGES", "REVIEW_ASSIGNED", "ROUND_NAMES", "farmer_message", "to_gsm"]

FARMER_MESSAGES = {
    "ai_likely": {
        "en": "AgriSense: Likely {disease} ({percent}%), not yet confirmed. An agrovet is checking. "
        "Now: remove spotted leaves, water at the base, do not spray yet.",
        "sw": "AgriSense: Huenda ni {disease} ({percent}%), bado haijathibitishwa. "
        "Muuzaji wa pembejeo anakagua. Sasa: ondoa majani yenye madoa, usinyunyizie dawa bado.",
    },
    "ai_healthy": {
        "en": "AgriSense: The computer found no disease in your photos. An agrovet will still check them. "
        "Do not spray yet.",
        "sw": "AgriSense: Kompyuta haikupata ugonjwa kwenye picha zako. Muuzaji wa pembejeo bado atazikagua. "
        "Usinyunyizie dawa bado.",
    },
    "received": {
        "en": "AgriSense: We received your report. An agrovet is checking your photos. Now: remove spotted "
        "leaves, water at the base, do not spray yet.",
        "sw": "AgriSense: Tumepokea ripoti yako. Muuzaji wa pembejeo anakagua picha zako. Sasa: ondoa majani "
        "yenye madoa, usinyunyizie dawa bado.",
    },
    "retake_not_plant": {
        "en": "AgriSense: We could not see a plant in your photos. Please open AgriSense and take new photos "
        "of the sick tomato plant.",
        "sw": "AgriSense: Hatukuona mmea kwenye picha zako. Tafadhali fungua AgriSense upige picha mpya za "
        "mmea wa nyanya ulio mgonjwa.",
    },
    "retake_not_tomato": {
        "en": "AgriSense: Your photos do not look like tomato. Please open AgriSense and take new photos of "
        "the sick tomato plant.",
        "sw": "AgriSense: Picha zako hazionekani kuwa za nyanya. Tafadhali fungua AgriSense upige picha mpya "
        "za mmea wa nyanya ulio mgonjwa.",
    },
    "confirmed": {
        "en": "AgriSense: Confirmed by {agrovet}: {disease}. Your agrovet is preparing a prescription.",
        "sw": "AgriSense: Imethibitishwa na {agrovet}: {disease}. Muuzaji wako wa pembejeo anaandaa agizo la "
        "dawa.",
    },
    "confirmed_corrected": {
        "en": "AgriSense: Confirmed by {agrovet}: {disease}. This differs from the computer suggestion; "
        "follow the agrovet. Prescription coming.",
        "sw": "AgriSense: Imethibitishwa na {agrovet}: {disease}. Ni tofauti na pendekezo la kompyuta; "
        "fuata muuzaji. Agizo la dawa linakuja.",
    },
    "unknown": {
        "en": "AgriSense: The agrovets could not agree on the problem. "
        "Please take a sample of the sick plant to the nearest plant clinic or extension officer.",
        "sw": "AgriSense: Wauzaji wa pembejeo hawakukubaliana kuhusu tatizo. "
        "Tafadhali peleka sampuli ya mmea mgonjwa kwenye kliniki ya mimea au kwa afisa wa kilimo.",
    },
    "signup_code": {
        "en": "AgriSense: Your code is {code}. It expires in {minutes} minutes. Do not share it with anyone.",
        "sw": "AgriSense: Nambari yako ni {code}. Itaisha baada ya dakika {minutes}. Usimpe mtu yeyote.",
    },
    "prescription": {
        "en": "AgriSense prescription {code}: {product}, {quantity}. Valid until {expires}. "
        "Show this code at a verified agrovet.",
        "sw": "AgriSense agizo la dawa {code}: {product}, {quantity}. Linatumika hadi {expires}. "
        "Onyesha nambari hii kwa muuzaji wa pembejeo aliyethibitishwa.",
    },
}

# Agrovets use the app in English.
REVIEW_ASSIGNED = (
    "AgriSense: New tomato case to review in {ward} ({round}). Please open AgriSense and confirm the "
    "diagnosis within {hours} hours."
)
ROUND_NAMES = {1: "first review", 2: "second opinion"}

# Typical values, used to check that each message (and each translation) fits its SMS limit.
SAMPLE_VALUES = {
    "disease": "Late blight",
    "percent": 98,
    "agrovet": "Chuka Farmers Agrovet",
    "code": "AGR-7F3K9Q",
    "product": "Ridomil Gold MZ 68 WG",
    "quantity": "use the rate on the label",  # the longest dose wording
    "expires": "17/10/2026",
    "minutes": 10,
}

_farmer = register(
    "sms.farmer",
    FARMER_MESSAGES,
    sms=True,
    # The prescription carries product and dose, so it may take two parts; everything else fits one.
    max_lengths={"prescription": 306},
    samples=SAMPLE_VALUES,
)


def farmer_message(key: str, language: str = "en", **values) -> str:
    return to_gsm(_farmer.text(key, language, **values))
