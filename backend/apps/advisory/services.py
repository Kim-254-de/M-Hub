"""Kikuyu (and other language) advice for a farmer's question about their case.

The model is grounded on the case facts only and never sees products or doses. Every answer is
checked by ``guard`` before the farmer sees it; a blocked answer is replaced by fixed text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from . import guard
from .context import CaseContext
from .messages import fallback_message
from .prompt import system_prompt, user_turn
from .providers import Provider, ProviderError, Reply, get_provider

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class Advice:
    text: str  # what the farmer sees
    raw_text: str  # what the model wrote (kept for review)
    language: str
    check: guard.GuardResult
    reply: Reply | None

    @property
    def blocked(self) -> bool:
        return self.check.blocked


def advise(
    context: CaseContext,
    question: str,
    *,
    language: str,
    provider: Provider | None = None,
    model: str | None = None,
    allow_fallback: bool = True,
    terms: list[str] | None = None,
) -> Advice:
    """Answer the farmer's question about their case, in their language. Raises ProviderError."""
    provider = provider or get_provider()
    reply = provider.reply(
        system=system_prompt(language),
        user=user_turn(context.describe(), question.strip()[:MAX_QUESTION_CHARS]),
        model=model or settings.ADVISORY["MODEL"],
        allow_fallback=allow_fallback,
    )
    result = guard.check(reply.text, terms)
    if result.blocked:
        logger.warning("Advice blocked by guard: %s", result.as_dict())
    text = fallback_message("blocked", language) if result.blocked or not reply.text else reply.text
    return Advice(text=text, raw_text=reply.text, language=language, check=result, reply=reply)


def advise_or_fallback(context: CaseContext, question: str, *, language: str, **kwargs) -> Advice:
    """For the app: never raises; tells the farmer to ask their agrovet if the model is unavailable."""
    try:
        return advise(context, question, language=language, **kwargs)
    except ProviderError:
        logger.exception("Advisory provider failed")
        text = fallback_message("unavailable", language)
        return Advice(text=text, raw_text="", language=language, check=guard.GuardResult(), reply=None)
