"""Tests for the commentary provider factory."""

from __future__ import annotations

import importlib.util

import pytest

from ai_caster.commentary.factory import create_provider
from ai_caster.commentary.providers.mock import MockProvider
from ai_caster.config.models import AIProvider, AISettings


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def test_default_is_mock():
    provider = create_provider(AISettings())
    assert isinstance(provider, MockProvider)


@pytest.mark.skipif(_installed("anthropic"), reason="anthropic installed; fallback path not hit")
def test_anthropic_falls_back_to_mock_without_sdk():
    provider = create_provider(AISettings(provider=AIProvider.ANTHROPIC))
    assert isinstance(provider, MockProvider)


@pytest.mark.skipif(_installed("openai"), reason="openai installed; fallback path not hit")
def test_openai_and_local_fall_back_to_mock_without_sdk():
    assert isinstance(create_provider(AISettings(provider=AIProvider.OPENAI)), MockProvider)
    assert isinstance(create_provider(AISettings(provider=AIProvider.LOCAL)), MockProvider)
