"""Fixed text the adviser falls back to. English and Kiswahili here; Kikuyu via apps.translations."""

from apps.translations.catalog import register

FALLBACK_MESSAGES = {
    "blocked": {
        "en": "I cannot advise on products or amounts. Follow your prescription card, or ask your agrovet.",
        "sw": "Siwezi kushauri kuhusu dawa au vipimo. Fuata kadi yako ya agizo la dawa, au muulize muuzaji "
        "wako wa pembejeo.",
    },
    "unavailable": {
        "en": "The adviser is not available right now. Please ask your agrovet, or try again later.",
        "sw": "Mshauri hapatikani kwa sasa. Tafadhali muulize muuzaji wako wa pembejeo, au jaribu tena "
        "baadaye.",
    },
}

_fallback = register("advisory", FALLBACK_MESSAGES, safety=True)


def fallback_message(key: str, language: str = "en") -> str:
    return _fallback.text(key, language)
