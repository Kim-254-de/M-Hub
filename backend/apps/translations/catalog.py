"""Farmer-facing text by key and language.

English and Kiswahili are written in each app's ``messages`` module, which registers them here.
Other languages (Kikuyu first) are human translations stored as ``Translation`` rows. A translation
is shown only after a reviewer approves it, and only while the English it was translated from is
unchanged. Otherwise the farmer gets the next language they read (``settings.LANGUAGE_FALLBACKS``),
never a machine translation (Documentation §11).
"""

from __future__ import annotations

import hashlib
import string
from dataclasses import dataclass, field

from django.conf import settings

from .gsm import is_plain_gsm, to_gsm

SMS_LENGTH = 160

_REGISTRY: dict[str, Source] = {}


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def placeholders(text: str) -> set[str]:
    """The ``{name}`` fields in a template. Raises ValueError for unbalanced braces."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


@dataclass(frozen=True)
class Source:
    key: str
    texts: dict[str, str]  # language -> text, as written in code
    sms: bool = False
    safety: bool = False  # doses, protective equipment, harvest intervals: never shown unreviewed
    max_length: int | None = None
    samples: dict = field(default_factory=dict)  # realistic values to check the SMS length

    @property
    def english(self) -> str:
        return self.texts["en"]

    @property
    def checksum(self) -> str:
        return checksum(self.english)

    def problems(self, text: str) -> list[str]:
        """Why ``text`` cannot stand in for this source, if it cannot."""
        if not text.strip():
            return ["The translation is empty."]
        try:
            fields = placeholders(text)
        except ValueError:
            return ["Unbalanced { or } in the translation."]
        expected = placeholders(self.english)
        errors = []
        if fields != expected:
            want = ", ".join(sorted(f"{{{f}}}" for f in expected)) or "none"
            errors.append(f"Placeholders must be exactly as in the English: {want}.")
        if self.sms and not errors:
            plain = to_gsm(text.format(**{f: self.samples.get(f, f) for f in fields}))
            if not is_plain_gsm(plain):
                odd = "".join(sorted({c for c in plain if not is_plain_gsm(c)}))
                errors.append(f"SMS text has characters outside plain GSM-7: {odd!r}.")
            elif self.max_length and len(plain) > self.max_length:
                errors.append(
                    f"SMS text is {len(plain)} characters with typical values; "
                    f"the limit is {self.max_length}."
                )
        return errors


def register(
    prefix: str,
    messages: dict[str, dict[str, str]],
    *,
    sms: bool = False,
    safety: bool = False,
    max_lengths: dict[str, int] | None = None,
    samples: dict | None = None,
) -> Catalog:
    """Register ``{name: {language: text}}`` under ``prefix`` and return a lookup for it."""
    for name, texts in messages.items():
        key = f"{prefix}.{name}"
        max_length = (max_lengths or {}).get(name, SMS_LENGTH if sms else None)
        _REGISTRY[key] = Source(key, dict(texts), sms, safety, max_length, dict(samples or {}))
    return Catalog(prefix)


def sources() -> list[Source]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get_source(key: str) -> Source | None:
    return _REGISTRY.get(key)


def language_chain(language: str) -> list[str]:
    """The farmer's language, then the ones they also read, then English."""
    chain = [language, *settings.LANGUAGE_FALLBACKS.get(language, []), "en"]
    return list(dict.fromkeys(chain))


def _approved(language: str, keys: list[str]) -> dict[str, str]:
    from .models import Translation

    rows = Translation.objects.filter(
        language=language, key__in=keys, status=Translation.Status.APPROVED
    ).values_list("key", "text", "source_checksum")
    return {key: text for key, text, source_checksum in rows if source_checksum == _REGISTRY[key].checksum}


def texts_in(keys: list[str], language: str) -> dict[str, str] | None:
    """All of ``keys`` in exactly ``language``, or None if any is missing."""
    found = {k: _REGISTRY[k].texts[language] for k in keys if language in _REGISTRY[k].texts}
    missing = [k for k in keys if k not in found]
    if missing and language != "en":
        found.update(_approved(language, missing))
    return found if len(found) == len(keys) else None


def resolve(keys: list[str], language: str) -> tuple[str, dict[str, str]]:
    """``keys`` in the first language of the chain that has all of them, so a screen never mixes languages."""
    for candidate in language_chain(language):
        found = texts_in(keys, candidate)
        if found is not None:
            return candidate, found
    raise KeyError(f"No English text for {keys}")  # every source has English


class Catalog:
    """The messages registered under one prefix."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def key(self, name: str) -> str:
        return f"{self.prefix}.{name}"

    def text(self, name: str, language: str = "en", **values) -> str:
        _, found = resolve([self.key(name)], language)
        return found[self.key(name)].format(**values)

    def group(self, names: list[str], language: str = "en") -> tuple[str, dict[str, str]]:
        """Templates for several names, all in one language: (language, {name: template})."""
        used, found = resolve([self.key(n) for n in names], language)
        return used, {n: found[self.key(n)] for n in names}

    def group_in(self, names: list[str], language: str) -> dict[str, str] | None:
        found = texts_in([self.key(n) for n in names], language)
        return None if found is None else {n: found[self.key(n)] for n in names}
