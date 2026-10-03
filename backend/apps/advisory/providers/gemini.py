"""Gemini via the Google Gemini API (google-genai SDK)."""

from __future__ import annotations

import time

from django.conf import settings
from google import genai
from google.genai import errors, types

from .base import Provider, ProviderError, Reply

# settings.ADVISORY["EFFORT"] -> Gemini thinking level.
THINKING_LEVELS = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}
BLOCKED = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, client: genai.Client | None = None, *, max_retries: int = 2):
        config = settings.ADVISORY
        if client is None:
            if not config["GEMINI_API_KEY"]:
                raise ProviderError("GEMINI_API_KEY is not set.")
            client = genai.Client(
                api_key=config["GEMINI_API_KEY"],
                http_options=types.HttpOptions(
                    timeout=int(config["TIMEOUT_S"] * 1000),  # milliseconds
                    retry_options=types.HttpRetryOptions(attempts=max_retries + 1),
                ),
            )
        self.client = client
        self.thinking_level = THINKING_LEVELS[config["EFFORT"]]
        self.max_tokens = config["MAX_TOKENS"]

    def reply(self, *, system: str, user: str, model: str, allow_fallback: bool = True) -> Reply:
        # Gemini has no server-side fallback; ``allow_fallback`` does not apply.
        started = time.monotonic()
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=self.max_tokens,
                    thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
                ),
            )
        except errors.APIError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            raise ProviderError(f"Gemini API error {exc.code}: {exc}", retryable=retryable) from exc
        latency = time.monotonic() - started

        candidate = response.candidates[0] if response.candidates else None
        finish = candidate.finish_reason.value if candidate and candidate.finish_reason else ""
        if candidate is None or finish in BLOCKED:
            stop_reason, text = "refusal", ""
        else:
            stop_reason = "max_tokens" if finish == "MAX_TOKENS" else "end_turn"
            parts = (candidate.content.parts if candidate.content else None) or []
            text = "".join(p.text for p in parts if p.text and not p.thought).strip()

        usage = response.usage_metadata
        return Reply(
            text=text,
            model=response.model_version or model,
            stop_reason=stop_reason,
            usage={
                "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
                # Thinking is billed as output, as it is for Claude.
                "output_tokens": ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
                if usage
                else 0,
                "cache_read_input_tokens": (usage.cached_content_token_count or 0) if usage else 0,
                "cache_creation_input_tokens": 0,
            },
            latency_s=round(latency, 2),
        )
