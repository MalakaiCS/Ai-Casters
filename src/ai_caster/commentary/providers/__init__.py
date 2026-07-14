"""Pluggable commentary providers — one interface, several backends."""

from ai_caster.commentary.providers.base import LLMProvider, LLMRequest
from ai_caster.commentary.providers.mock import MockProvider

__all__ = ["LLMProvider", "LLMRequest", "MockProvider"]
