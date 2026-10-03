"""Farmer-facing diagnosis status messages, keyed by case status and language.

English and Kiswahili are written here; other languages are reviewed translations (apps.translations).
"""

from apps.cases.models import Case
from apps.translations.catalog import language_chain, register

STATUS_MESSAGES = {
    Case.Status.REPORTED: {
        "en": "We are checking your photos.",
        "sw": "Tunakagua picha zako.",
    },
    Case.Status.DIAGNOSING: {
        "en": "A verified agrovet is reviewing your case.",
        "sw": "Muuzaji wa pembejeo aliyethibitishwa anakagua tatizo lako.",
    },
    Case.Status.SECOND_OPINION: {
        "en": "A second verified agrovet is checking your case to make sure the diagnosis is right.",
        "sw": "Muuzaji wa pili wa pembejeo aliyethibitishwa anakagua tatizo lako ili kuhakikisha "
        "utambuzi ni sahihi.",
    },
    Case.Status.DIAGNOSED: {
        "en": "Your crop problem has been confirmed: {disease}.",
        "sw": "Tatizo la zao lako limethibitishwa: {disease}.",
    },
    Case.Status.UNKNOWN: {
        "en": "The agrovets could not agree on what is wrong with your crop. Please take a sample of the "
        "sick plant to your nearest plant clinic or agricultural extension officer.",
        "sw": "Wauzaji wa pembejeo hawakukubaliana kuhusu tatizo la zao lako. Tafadhali peleka sampuli ya "
        "mmea mgonjwa kwenye kliniki ya mimea au kwa afisa wa kilimo aliye karibu nawe.",
    },
}


# Provisional AI result shown while the farmer waits for the agrovet. Never names a product.
PROVISIONAL_MESSAGES = {
    "likely": {
        "en": "Likely {disease} ({percent}%). This is a computer suggestion, not a final diagnosis. "
        "A verified agrovet is confirming it.",
        "sw": "Huenda ni {disease} ({percent}%). Haya ni mapendekezo ya kompyuta, si utambuzi wa mwisho. "
        "Muuzaji wa pembejeo aliyethibitishwa anathibitisha.",
    },
    "unsure": {
        "en": "The computer could not tell clearly what is wrong. A verified agrovet will check your photos.",
        "sw": "Kompyuta haikuweza kutambua wazi tatizo ni nini. Muuzaji wa pembejeo aliyethibitishwa "
        "atakagua picha zako.",
    },
    "healthy": {
        "en": "The computer did not find a disease in these photos. "
        "A verified agrovet will still check them.",
        "sw": "Kompyuta haikupata ugonjwa kwenye picha hizi. Muuzaji wa pembejeo aliyethibitishwa bado "
        "atazikagua.",
    },
}

AI_CORRECTED_MESSAGES = {
    "en": "The agrovet's diagnosis is different from the first computer suggestion. "
    "Follow the agrovet's diagnosis.",
    "sw": "Utambuzi wa muuzaji wa pembejeo ni tofauti na mapendekezo ya kwanza ya kompyuta. Fuata utambuzi "
    "wa muuzaji wa pembejeo.",
}

# Product-free first steps for a sick tomato crop, shown when the disease has no reviewed steps of its own.
GENERAL_SAFE_ACTIONS = {
    "en": [
        "Remove leaves and fruit with spots. Bury them or burn them away from the field. "
        "Do not leave them in the field or put them in compost.",
        "Water at the base of the plants in the morning. Do not pour or spray water over the leaves.",
        "Do not work among the plants while they are wet.",
        "Wash your hands and tools after touching sick plants, before you touch healthy ones.",
        "Do not spray any chemical until the agrovet confirms the problem.",
    ],
    "sw": [
        "Ondoa majani na matunda yenye madoa. Yazike au yachome mbali na shamba. Usiyaache shambani wala "
        "kuyaweka kwenye mboji.",
        "Mwagilia maji kwenye shina la mmea asubuhi. Usimwagie wala kunyunyizia maji juu ya majani.",
        "Usifanye kazi kati ya mimea ikiwa imelowa.",
        "Osha mikono na vifaa vyako baada ya kugusa mimea migonjwa, kabla ya kugusa mimea mizima.",
        "Usinyunyizie dawa yoyote hadi muuzaji wa pembejeo athibitishe tatizo.",
    ],
}


OUTBREAK_MESSAGES = {
    "near_ward": {
        "en": "{disease} confirmed by {count} farmers near {ward} this week. Check your crop.",
        "sw": "{disease} imethibitishwa na wakulima {count} karibu na {ward} wiki hii. Kagua zao lako.",
    },
    "nearby": {
        "en": "{disease} confirmed by {count} farmers near you this week. Check your crop.",
        "sw": "{disease} imethibitishwa na wakulima {count} karibu nawe wiki hii. Kagua zao lako.",
    },
}

_status = register("diagnosis.status", STATUS_MESSAGES)
_outbreak = register("diagnosis.outbreak", OUTBREAK_MESSAGES)
_provisional = register("diagnosis.provisional", PROVISIONAL_MESSAGES)
_corrected = register("diagnosis", {"ai_corrected": AI_CORRECTED_MESSAGES})
_SAFE_ACTION_NAMES = [str(i) for i in range(len(GENERAL_SAFE_ACTIONS["en"]))]
_safe_actions = register(
    "diagnosis.safe_actions",
    {
        name: {lang: steps[int(name)] for lang, steps in GENERAL_SAFE_ACTIONS.items()}
        for name in _SAFE_ACTION_NAMES
    },
    safety=True,
)


def provisional_message(kind: str, language: str = "en", **values) -> str:
    return _provisional.text(kind, language, **values)


def ai_corrected_message(language: str = "en") -> str:
    return _corrected.text("ai_corrected", language)


def general_safe_actions(language: str = "en") -> list[str]:
    _, steps = _safe_actions.group(_SAFE_ACTION_NAMES, language)
    return [steps[name] for name in _SAFE_ACTION_NAMES]


def safe_actions(disease, language: str = "en") -> list[str]:
    """First steps in the first language the farmer reads: the disease's own, else the general ones."""
    for candidate in language_chain(language):
        steps = disease.actions_for(candidate) if disease else []
        if steps:
            return steps
        general = _safe_actions.group_in(_SAFE_ACTION_NAMES, candidate)
        if general:
            return [general[name] for name in _SAFE_ACTION_NAMES]
    return general_safe_actions("en")


def status_message(status: str, language: str = "en", **values) -> str | None:
    if status not in STATUS_MESSAGES:
        return None
    return _status.text(status, language, **values)


def outbreak_message(language: str, *, disease: str, count: int, ward: str) -> str:
    if ward:
        return _outbreak.text("near_ward", language, disease=disease, count=count, ward=ward)
    return _outbreak.text("nearby", language, disease=disease, count=count)
