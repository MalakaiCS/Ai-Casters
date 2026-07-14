"""Anthropic-backed commentary provider (optional).

Uses the official ``anthropic`` SDK's Messages API. Lazy-imports the SDK so it is
only required when this provider is actually selected (the ``[ai]`` extra).

Notes specific to current Claude models, honoured here:
- No ``temperature``/``top_p`` — those are rejected (400) on Opus 4.8/4.7, so we
  don't send them.
- ``thinking`` is omitted; on Opus 4.8 that runs without extended thinking, and
  the system prompt's "output only the line" instruction keeps the response to
  the spoken line.
"""

from __future__ import annotations

from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.core.logging import get_logger

_log = get_logger("commentary.anthropic")

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicProvider:
    """Generates commentary via the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str = "", default_model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._default_model = default_model or DEFAULT_MODEL
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore
            except ImportError as exc:  # pragma: no cover - only without the SDK
                raise RuntimeError(
                    "The Anthropic provider requires the 'anthropic' package. "
                    'Install AI extras: pip install "ai-esports-caster[ai]"'
                ) from exc
            # api_key="" -> let the SDK resolve credentials from the environment.
            self._client = anthropic.Anthropic(api_key=self._api_key or None)
        return self._client

    def generate(self, request: LLMRequest) -> str:
        client = self._ensure_client()
        response = client.messages.create(
            model=request.model or self._default_model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
        )
        if getattr(response, "stop_reason", None) == "refusal":
            _log.warning("Anthropic declined to generate a commentary line")
            return ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
        return ""
