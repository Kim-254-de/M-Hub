"""PCPB registration numbers: parsing from free text (OCR output) and normalising.

Labels print numbers like "PCPB (CR) 0856" or "PCPB(CR)0856". OCR commonly
confuses B/8 and O/0, I/l/1, S/5 and drops spaces or brackets, so matching
is tolerant and compares a canonical key: "<CATEGORY>:<number without leading zeros>".
"""

import re

_PATTERN = re.compile(
    r"P\s*C\s*P\s*[B8]\s*[\(\[{]?\s*([A-Z]{2,4})\s*[\)\]}]?\s*[.:\-/]?\s*([0-9OoIlSs]{3,6})(?![0-9])",
    re.IGNORECASE,
)
_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "s": "5"})


def make_key(category: str, number: str) -> str:
    digits = number.translate(_DIGIT_FIXES)
    return f"{category.upper()}:{int(digits)}"


def parse_reg_no(value: str) -> str | None:
    """Canonical key for one registration number, or None if it is not one."""
    match = _PATTERN.search(value or "")
    return make_key(*match.groups()) if match else None


def extract_keys(text: str) -> list[str]:
    """All registration-number keys found in ``text``, in order, without duplicates."""
    seen = []
    for category, number in _PATTERN.findall(text or ""):
        key = make_key(category, number)
        if key not in seen:
            seen.append(key)
    return seen
