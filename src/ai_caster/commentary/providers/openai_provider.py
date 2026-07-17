"""OpenAI-compatible commentary provider (optional).

Covers both the ``openai`` and ``local`` provider selections: a ``base_url``
override points the same client at a local OpenAI-compatible server (e.g. an
on-box LLM). Lazy-imports the ``openai`` SDK (the ``[ai]`` extra). A model id
must be configured — this provider has no built-in default model.
"""

from __future__ import annotations

from ai_caster.commentary.providers.base import LLMRequest
from ai_caster.core.logging import get_logger

_log = get_logger("commentary.openai")


class OpenAIProvider:
    """Generates commentary via an OpenAI-compatible chat completions API."""

    name = "openai"

    def __init__(self, api_key: str = "", base_url: str = "", default_model: str = "") -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import openai  # type: ignore
            except ImportError as exc:  # pragma: no cover - only without the SDK
                raise RuntimeError(
                    "The OpenAI/local provider requires the 'openai' package. "
                    'Install AI extras: pip install "ai-esports-caster[ai]"'
                ) from exc
            kwargs = {"api_key": self._api_key or "not-needed"}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def generate(self, request: LLMRequest) -> str:
        model = request.model or self._default_model
        if not model:
            raise RuntimeError("No model configured for the OpenAI/local provider.")
        client = self._ensure_client()
        response = client.chat.completions.create(
            model=model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        return (content or "").strip()
