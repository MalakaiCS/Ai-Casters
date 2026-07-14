"""Tests for baked-in deployment defaults (pre-configured builds)."""

from __future__ import annotations

from pathlib import Path

from ai_caster.config.deploy import apply_deploy_defaults, deploy_overrides
from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import AccountProvider, AppSettings
from ai_caster.core.events import EventBus

_ENV_URL = "AI_CASTER_SUPABASE_URL"
_ENV_KEY = "AI_CASTER_SUPABASE_ANON_KEY"


def test_no_overrides_by_default(monkeypatch):
    monkeypatch.delenv(_ENV_URL, raising=False)
    monkeypatch.delenv(_ENV_KEY, raising=False)
    assert deploy_overrides() == {}
    base = AppSettings()
    assert apply_deploy_defaults(base) is base  # unchanged


def test_env_overrides_set_supabase(monkeypatch):
    monkeypatch.setenv(_ENV_URL, "https://demo.supabase.co")
    monkeypatch.setenv(_ENV_KEY, "anon-abc")
    merged = apply_deploy_defaults(AppSettings())
    assert merged.account.provider is AccountProvider.SUPABASE
    assert merged.account.supabase_url == "https://demo.supabase.co"
    assert merged.account.supabase_anon_key == "anon-abc"
    # Unrelated settings are untouched.
    assert merged.gsi.port == AppSettings().gsi.port


def test_partial_env_is_ignored(monkeypatch):
    monkeypatch.setenv(_ENV_URL, "https://demo.supabase.co")
    monkeypatch.delenv(_ENV_KEY, raising=False)
    assert deploy_overrides() == {}


def test_fresh_settings_apply_deploy_defaults(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(_ENV_URL, "https://demo.supabase.co")
    monkeypatch.setenv(_ENV_KEY, "anon-abc")
    manager = SettingsManager(tmp_path / "settings.json", EventBus())
    settings = manager.load()  # no file yet -> defaults + deploy overrides
    assert settings.account.provider is AccountProvider.SUPABASE
    assert settings.account.supabase_url == "https://demo.supabase.co"
    # And they were persisted.
    assert (tmp_path / "settings.json").exists()


def test_existing_settings_are_not_overridden(monkeypatch, tmp_path: Path):
    # Write a user file that stays offline.
    path = tmp_path / "settings.json"
    SettingsManager(path, EventBus()).load()  # creates default offline file (no env)
    monkeypatch.setenv(_ENV_URL, "https://demo.supabase.co")
    monkeypatch.setenv(_ENV_KEY, "anon-abc")
    # Reloading an existing file must not apply deploy defaults over the user's file.
    reloaded = SettingsManager(path, EventBus()).load()
    assert reloaded.account.provider is AccountProvider.OFFLINE
