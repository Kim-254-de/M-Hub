"""Crop disease identification via Kindwise crop.health.

If CROP_HEALTH_API_KEY is empty the service runs in demo mode and returns a
canned result, so the whole WhatsApp flow can be shown without an API key.
"""
import base64
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings

log = logging.getLogger(__name__)

DETAILS = "common_names,description,treatment,symptoms,severity"


@dataclass
class CropResult:
    ok: bool
    is_plant: bool = True
    disease: str = ""
    confidence: float = 0.0
    description: str = ""
    treatment: dict = field(default_factory=dict)  # {"chemical": [...], "biological": [...], "prevention": [...]}
    alternatives: list = field(default_factory=list)  # [(name, prob), ...]
    detected_crop: str = ""
    raw: dict = field(default_factory=dict)
    error: str = ""


def _demo_result(crop):
    demo = {
        "tomato": "late blight",
        "potato": "late blight",
        "maize": "fall armyworm",
        "beans": "bean rust",
        "coffee": "coffee leaf rust",
        "kale": "downy mildew",
        "cabbage": "downy mildew",
    }
    disease = demo.get((crop or "").lower(), "leaf spot")
    return CropResult(
        ok=True,
        disease=disease,
        confidence=0.82,
        description=f"(Demo mode) Typical {disease} symptoms detected on the {crop or 'crop'} leaf.",
        treatment={
            "prevention": [
                "Remove and destroy badly affected leaves.",
                "Rotate crops and avoid overhead watering in the evening.",
            ],
        },
        alternatives=[("leaf spot", 0.08)],
        raw={"demo": True},
    )


def identify(image_bytes, mime="image/jpeg", crop="", latitude=None, longitude=None):
    if not settings.CROP_HEALTH_API_KEY:
        return _demo_result(crop)

    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    body = {"images": [data_uri], "similar_images": False}
    if latitude is not None and longitude is not None:
        body.update(latitude=latitude, longitude=longitude)
    try:
        r = requests.post(
            settings.CROP_HEALTH_URL,
            params={"details": DETAILS, "language": "en"},
            json=body,
            headers={"Api-Key": settings.CROP_HEALTH_API_KEY, "Content-Type": "application/json"},
            timeout=60,
        )
        if r.status_code >= 400:
            log.error("crop.health error %s: %s", r.status_code, r.text[:500])
            return CropResult(ok=False, error=f"HTTP {r.status_code}")
        return parse(r.json())
    except (requests.RequestException, ValueError) as exc:
        log.error("crop.health request failed: %s", exc)
        return CropResult(ok=False, error=str(exc))


def parse(payload):
    result = payload.get("result") or {}
    is_plant = result.get("is_plant") or {}
    plant_ok = is_plant.get("binary", True) if isinstance(is_plant, dict) else True

    crops = (result.get("crop") or {}).get("suggestions") or []
    diseases = (result.get("disease") or {}).get("suggestions") or []
    if not diseases:
        return CropResult(ok=True, is_plant=plant_ok, raw=payload,
                          detected_crop=crops[0].get("name", "") if crops else "")

    top = diseases[0]
    details = top.get("details") or {}
    names = details.get("common_names") or []
    disease = (names[0] if names else top.get("name", "")).strip()

    description = details.get("description") or ""
    if isinstance(description, dict):
        description = description.get("value", "")

    treatment = details.get("treatment") or {}
    if not isinstance(treatment, dict):
        treatment = {}

    return CropResult(
        ok=True,
        is_plant=plant_ok,
        disease=disease,
        confidence=float(top.get("probability") or 0),
        description=description,
        treatment={k: v for k, v in treatment.items() if isinstance(v, list)},
        alternatives=[(d.get("name", ""), float(d.get("probability") or 0)) for d in diseases[1:3]],
        detected_crop=crops[0].get("name", "") if crops else "",
        raw=payload,
    )


def format_treatment(treatment, limit=3):
    """Prevention steps only.

    Provider chemical/biological advice names products that may not be PCPB-registered
    for the crop in Kenya, so it is never shown (Documentation §11: registered products
    only; products come from the agrovet's prescription, never from the AI).
    """
    items = (treatment or {}).get("prevention") or []
    return "\n".join(f"• {i}" for i in items[:limit])
