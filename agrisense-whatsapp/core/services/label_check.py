"""Check a product label against the PCPB register (Documentation §6.4, step 4).

The farmer photographs the label (or types the number). We read the PCPB
registration number and compare it with the register and with what was ordered.
Matching mirrors backend/apps/products/pcpb.py: OCR often confuses B/8, O/0,
I/l/1, S/5 and drops brackets, so numbers are compared as "<CATEGORY>:<int>".

Without OCRSPACE_API_KEY, photos cannot be read; the farmer is asked to type
the number instead, so the demo still works offline.
"""
import logging
import re
from dataclasses import dataclass

import requests
from django.conf import settings

from core.models import Order, Product

log = logging.getLogger(__name__)

_PATTERN = re.compile(
    r"P\s*C\s*P\s*[B8]\s*[\(\[{]?\s*([A-Z]{2,4})\s*[\)\]}]?\s*[.:\-/]?\s*([0-9OoIlSs]{3,6})(?![0-9])",
    re.IGNORECASE,
)
_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "s": "5"})


def reg_key(text):
    """Canonical key of the first PCPB number in ``text``, or ''."""
    match = _PATTERN.search(text or "")
    if not match:
        return ""
    category, number = match.groups()
    return f"{category.upper()}:{int(number.translate(_DIGIT_FIXES))}"


@dataclass
class LabelResult:
    result: str  # one of Order.LABEL_* or "unreadable"
    reg_no: str = ""
    product: Product = None


def read_label_text(image_bytes):
    """Text on the label via OCR.space, or None if OCR is not configured or fails."""
    if not settings.OCRSPACE_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            headers={"apikey": settings.OCRSPACE_API_KEY},
            files={"file": ("label.jpg", image_bytes, "image/jpeg")},
            data={"language": "eng", "OCREngine": "2", "scale": "true", "detectOrientation": "true"},
            timeout=30,
        )
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.error("OCR request failed: %s", exc)
        return None
    if data.get("IsErroredOnProcessing"):
        log.error("OCR error: %s", data.get("ErrorMessage"))
        return None
    return "\n".join(p.get("ParsedText", "") for p in data.get("ParsedResults") or [])


def check(order: Order, text: str) -> LabelResult:
    """Classify the label text for this order."""
    key = reg_key(text)
    if not key:
        return LabelResult("unreadable")
    reg_no = _PATTERN.search(text).group(0).strip()
    if reg_key(order.product.pcpb_reg_no) == key:
        return LabelResult(Order.LABEL_VERIFIED, reg_no, order.product)
    # The demo register is every product listed by a verified agrovet.
    for product in Product.objects.filter(agrovet__is_verified=True).exclude(pcpb_reg_no=""):
        if reg_key(product.pcpb_reg_no) == key:
            return LabelResult(Order.LABEL_NOT_PRESCRIBED, reg_no, product)
    return LabelResult(Order.LABEL_NOT_REGISTERED, reg_no)
