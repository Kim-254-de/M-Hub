"""Claude via the Anthropic API."""

from __future__ import annotations

import time

import anthropic
from django.conf import settings

from .base import Provider, ProviderError, Reply

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(self, client: anthropic.Anthropic | None = None, *, max_retries: int = 2):
        config = settings.ADVISORY
        self.client = client or anthropic.Anthropic(timeout=config["TIMEOUT_S"], max_retries=max_retries)
        self.effort = config["EFFORT"]
        self.max_tokens = config["MAX_TOKENS"]

    def reply(self, *, system: str, user: str, model: str, allow_fallback: bool = True) -> Reply:
        params = {
            "model": model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }
        started = time.monotonic()
        try:
            if allow_fallback:
                # On a safety decline the API answers with Anthropic's recommended fallback model.
                response = self.client.beta.messages.create(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self.client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"Rate limited: {exc}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"API error {exc.status_code}: {exc}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"Connection error: {exc}", retryable=True) from exc
        latency = time.monotonic() - started

        text = (
            ""
            if response.stop_reason == "refusal"
            else "".join(block.text for block in response.content if block.type == "text").strip()
        )
        usage = response.usage
        iterations = getattr(usage, "iterations", None) or []
        return Reply(
            text=text,
            model=response.model,
            stop_reason=response.stop_reason or "",
            usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
            },
            latency_s=round(latency, 2),
            fell_back=any(getattr(i, "type", "") == "fallback_message" for i in iterations),
        )
