"""Keeping SMS text in the GSM-7 alphabet.

Any character outside it switches the whole message to UCS-2, where one SMS holds 70 characters
instead of 160.
"""

# Common characters outside GSM-7: copied quotes and dashes, and the Kikuyu tilde vowels, which
# Kikuyu SMS conventionally writes without the tilde.
_REPLACEMENTS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
        "ĩ": "i",
        "Ĩ": "I",
        "ũ": "u",
        "Ũ": "U",
    }
)

# Characters that would force UCS-2 (70 per SMS) or count double in GSM-7.
NOT_PLAIN_GSM = set("`[]{}\\^~|")


def to_gsm(text: str) -> str:
    return text.translate(_REPLACEMENTS)


def is_plain_gsm(text: str) -> bool:
    return all(32 <= ord(c) < 127 for c in text) and not set(text) & NOT_PLAIN_GSM
