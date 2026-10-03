"""Farmer-facing advice after each check-in, by situation and language. Never names a product.

English and Kiswahili are written here; other languages are reviewed translations (apps.translations).
"""

from apps.translations.catalog import register

ADVICE = {
    "spreading": {
        "en": "The spread has not stopped. Do not spray again on your own. Visit your agrovet with your case "
        "code; the product may not be working here.",
        "sw": "Ugonjwa bado unaenea. Usinyunyizie tena peke yako. "
        "Mtembelee muuzaji wako wa pembejeo ukiwa na nambari ya tatizo lako; huenda dawa haifanyi kazi hapa.",
    },
    "fewer": {
        "en": "Some new spots are still appearing. Keep removing spotted leaves and check your crop again on "
        "day {next_day}.",
        "sw": "Madoa machache mapya bado yanatokea. Endelea kuondoa majani yenye madoa "
        "na ukague zao lako tena siku ya {next_day}.",
    },
    "stopped": {
        "en": "Good: no new spots. Check your crop again on day {next_day}.",
        "sw": "Vizuri: hakuna madoa mapya. Kagua zao lako tena siku ya {next_day}.",
    },
    "complete": {
        "en": "Thank you. Your report helps farmers near you choose what works.",
        "sw": "Asante. Ripoti yako inawasaidia wakulima walio karibu nawe kuchagua kinachofanya kazi.",
    },
}


_advice = register("followups.advice", ADVICE, safety=True)


def advice(key: str, language: str = "en", **values) -> str:
    return _advice.text(key, language, **values)
