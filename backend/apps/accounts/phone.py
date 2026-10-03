import re

_KENYAN_MOBILE = re.compile(r"^(?:\+?254|0)?([17]\d{8})$")


def normalize_kenyan_phone(value: str) -> str | None:
    """Return a Kenyan mobile number as +2547XXXXXXXX / +2541XXXXXXXX, or None if invalid.

    Accepts the forms farmers actually type: 0712 345 678, 254712345678, +254-712-345678.
    """
    digits = re.sub(r"[\s\-().]", "", value or "")
    match = _KENYAN_MOBILE.match(digits)
    return f"+254{match.group(1)}" if match else None
