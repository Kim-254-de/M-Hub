import re


def normalize_phone(raw):
    """Return a Kenyan number as 2547XXXXXXXX / 2541XXXXXXXX, or '' if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    if re.fullmatch(r"254[71]\d{8}", digits):
        return digits
    return ""
