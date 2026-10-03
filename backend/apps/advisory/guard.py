"""Automatic check of an answer before a farmer sees it (Documentation §11).

Blocks answers that name a pesticide product or active ingredient, or that give an amount. Flags
day counts for review (they may be a spray interval or a harvest wait). Numbers written as words
in Kikuyu are not caught here; the human evaluation covers those.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from apps.products.models import Product

# Active ingredients and brands sold for tomato blight in Kenya, beyond what the product register holds.
KNOWN_TERMS = [
    "mancozeb", "metalaxyl", "mefenoxam", "chlorothalonil", "copper oxychloride", "copper hydroxide",
    "cuprous oxide", "propineb", "cymoxanil", "dimethomorph", "azoxystrobin", "difenoconazole",
    "mandipropamid", "fluopicolide", "propamocarb", "famoxadone", "fosetyl", "iprodione", "tebuconazole",
    "ridomil", "dithane", "milraz", "victory", "mistress", "ortiva", "revus", "infinito", "equation pro",
    "daconil", "bravo", "kocide", "funguran", "antracol", "agrithane", "linkmil", "folicur",
]  # fmt: skip

# A number followed by a unit of amount, in English, Kiswahili or Kikuyu spellings.
_AMOUNT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:ml|mls|millilit(?:re|er)s?|g|gm|grams?|gramu|kg|kilos?|l|lit(?:re|er)s?|lita|"
    r"ndita|cc|tablespoons?|teaspoons?|vijiko|kijiko|caps?|vifuniko|kifuniko|sachets?|packets?|pakiti)\b",
    re.IGNORECASE,
)
_DAYS = re.compile(
    r"\b\d+\s*(?:days?|siku|mĩthenya|mithenya|weeks?|wiki)\b|\b(?:siku|mĩthenya|mithenya)\s+\d+\b", re.I
)


def _fold(text: str) -> str:
    """Lower case without accents, so "Mĩthenya" matches "mithenya"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def blocked_terms() -> list[str]:
    terms = set(KNOWN_TERMS)
    for name, ingredients in Product.objects.values_list("name", "active_ingredients"):
        terms.add(name.split("(")[0].strip().lower())
        terms.update(str(i).lower() for i in ingredients or [])
    return sorted(t for t in terms if len(t) >= 4)


@dataclass(frozen=True)
class GuardResult:
    products: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    days: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.products or self.amounts)

    def as_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "products": self.products,
            "amounts": self.amounts,
            "days": self.days,
        }


def check(text: str, terms: list[str] | None = None) -> GuardResult:
    folded = _fold(text)
    terms = blocked_terms() if terms is None else terms
    products = [t for t in terms if re.search(rf"\b{re.escape(_fold(t))}\b", folded)]
    return GuardResult(
        products=products,
        amounts=[m.group(0) for m in _AMOUNT.finditer(text)],
        days=[m.group(0) for m in _DAYS.finditer(text)],
    )
