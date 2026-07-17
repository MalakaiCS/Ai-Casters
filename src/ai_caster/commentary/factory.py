"""Build the commentary provider from settings.

Selecting a real provider whose SDK isn't installed degrades to the offline mock
rather than crashing, so an unattended broadcast keeps talking even if the AI
backend is misconfigured.
"""

from __future__ import annotations

import importlib.util

from ai_caster.commentary.providers.base import LLMProvider
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.config.models import AIProvider, AISettings
from ai_caster.core.logging import get_logger

_log = get_logger("commentary.factory")


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def create_provider(settings: AISettings) -> LLMProvider:
    """Construct the configured provider, or Mock if it isn't usable."""
    provider = settings.provider

    if provider is AIProvider.ANTHROPIC:
        if not _available("anthropic"):
            _log.warning("anthropic SDK not installed; falling back to mock commentary.")
            return MockProvider()
        from ai_caster.commentary.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.api_key)

    if provider in (AIProvider.OPENAI, AIProvider.LOCAL):
        if not _available("openai"):
            _log.warning("openai SDK not installed; falling back to mock commentary.")
            return MockProvider()
        from ai_caster.commentary.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.api_key, base_url=settings.base_url)

    return MockProvider()
