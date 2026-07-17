"""Tests for the build-baked account overlay (fixes sign-in on upgraded installs)."""

from __future__ import annotations

import ai_caster.app as app_mod
from ai_caster.app import Application
from ai_caster.config.models import AccountProvider, AccountSettings

BAKED = {
    "account": {
        "provider": "supabase",
        "supabase_url": "https://demo.supabase.co",
        "supabase_anon_key": "anon-key",
    }
}


def test_overlay_applies_baked_supabase_over_offline(monkeypatch):
    monkeypatch.setattr(app_mod, "deploy_overrides", lambda: BAKED)
    account = AccountSettings()  # default provider = offline
    effective = Application._effective_account(account)
    assert effective.provider is AccountProvider.SUPABASE
    assert effective.supabase_url == "https://demo.supabase.co"
    assert effective.supabase_anon_key == "anon-key"


def test_overlay_keeps_user_configured_supabase(monkeypatch):
    monkeypatch.setattr(app_mod, "deploy_overrides", lambda: BAKED)
    account = AccountSettings(
        provider=AccountProvider.SUPABASE,
        supabase_url="https://mine.supabase.co",
        supabase_anon_key="mine",
    )
    effective = Application._effective_account(account)
    # A user's own Supabase config is not overwritten by the baked one.
    assert effective.supabase_url == "https://mine.supabase.co"


def test_overlay_noop_without_baked_defaults(monkeypatch):
    monkeypatch.setattr(app_mod, "deploy_overrides", dict)
    account = AccountSettings()
    effective = Application._effective_account(account)
    assert effective.provider is AccountProvider.OFFLINE
