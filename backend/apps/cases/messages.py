"""Farmer-facing retake prompts, keyed by reason code and language.

Kept as plain text so the same strings serve the app and, later, WhatsApp.
"""

RETAKE_MESSAGES = {
    "invalid_image": {
        "en": "We could not open this photo. Please take it again.",
        "sw": "Hatukuweza kufungua picha hii. Tafadhali piga picha tena.",
    },
    "too_small": {
        "en": "This photo is too small. Use the phone camera and take the photo again.",
        "sw": "Picha hii ni ndogo sana. Tumia kamera ya simu na upige picha tena.",
    },
    "too_dark": {
        "en": "This photo is too dark. Move to a place with more light and take it again.",
        "sw": "Picha hii ina giza sana. Nenda mahali penye mwanga zaidi na upige picha tena.",
    },
    "blurry": {
        "en": "This photo is blurry. Hold the phone still, tap the leaf to focus, and take it again.",
        "sw": "Picha hii haiko wazi. Shikilia simu bila kutikisika, gusa jani ili lionekane wazi, "
        "kisha upige picha tena.",
    },
    "not_plant": {
        "en": "We could not see a plant in these photos. Please take clear photos of the sick tomato plant.",
        "sw": "Hatukuona mmea kwenye picha hizi. Tafadhali piga picha wazi za mmea wa nyanya ulio mgonjwa.",
    },
    "not_tomato": {
        "en": "This plant does not look like tomato. AgriSense currently supports tomato only. "
        "Please take photos of a tomato plant.",
        "sw": "Mmea huu hauonekani kuwa nyanya. Kwa sasa AgriSense inahudumia nyanya pekee. "
        "Tafadhali piga picha za mmea wa nyanya.",
    },
}


def retake_message(reason: str, language: str = "en") -> str:
    messages = RETAKE_MESSAGES.get(reason, RETAKE_MESSAGES["invalid_image"])
    return messages.get(language) or messages["en"]
