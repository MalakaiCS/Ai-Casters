"""Tests for the shared style hub (publish/pull trained profiles)."""

from __future__ import annotations

import ai_caster.training.hub as hub_mod
from ai_caster.config.models import AccountProvider, AccountSettings
from ai_caster.core.http import HttpError
from ai_caster.training.hub import (
    NullStyleHub,
    SupabaseStyleHub,
    create_style_hub,
)
from ai_caster.training.models import PacingProfile, StyleProfile

URL = "https://demo.supabase.co"
KEY = "anon-key"
TOKEN = "tok"

PROFILE = StyleProfile(
    num_sources=3, total_segments=250, pacing=PacingProfile(avg_gap_seconds=0.9)
)


def test_roundtrip_from_row():
    row = [{"profile": PROFILE.to_dict(), "summary": "v1", "published_at": "2026-07-16T00:00:00Z"}]
    shared = SupabaseStyleHub._shared_from_row(row)
    assert shared is not None
    assert shared.profile.total_segments == 250
    assert shared.summary == "v1"


def test_shared_from_row_handles_garbage():
    assert SupabaseStyleHub._shared_from_row([]) is None
    assert SupabaseStyleHub._shared_from_row([{"profile": "nope"}]) is None
    assert SupabaseStyleHub._shared_from_row(None) is None


def test_fetch_latest(monkeypatch):
    calls = {}

    def fake_get(url, *, headers=None, timeout=8.0):
        calls["url"] = url
        return [{"profile": PROFILE.to_dict(), "summary": "latest", "published_at": "x"}]

    monkeypatch.setattr(hub_mod, "get_json", fake_get)
    shared = SupabaseStyleHub(URL, KEY).fetch_latest(token=TOKEN)
    assert shared.summary == "latest"
    assert "order=published_at.desc" in calls["url"]
    assert "limit=1" in calls["url"]


def test_publish_posts_profile(monkeypatch):
    calls = {}

    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        calls["url"] = url
        calls["payload"] = payload
        return {}

    monkeypatch.setattr(hub_mod, "post_json", fake_post)
    result = SupabaseStyleHub(URL, KEY).publish(PROFILE, "my publish", token=TOKEN)
    assert result.ok
    assert calls["url"].endswith("/rest/v1/style_hub")
    assert calls["payload"]["summary"] == "my publish"
    assert calls["payload"]["profile"]["total_segments"] == 250


def test_publish_forbidden_is_friendly(monkeypatch):
    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        raise HttpError("no", status=403)

    monkeypatch.setattr(hub_mod, "post_json", fake_post)
    result = SupabaseStyleHub(URL, KEY).publish(PROFILE, "x", token=TOKEN)
    assert not result.ok
    assert "Staff" in result.error


def test_null_hub_is_unsupported():
    hub = NullStyleHub()
    assert hub.supported is False
    assert hub.fetch_latest(token="x") is None
    assert not hub.publish(PROFILE, "x", token="x").ok


def test_factory_selects_supabase_or_null():
    supa = create_style_hub(
        AccountSettings(provider=AccountProvider.SUPABASE, supabase_url=URL, supabase_anon_key=KEY)
    )
    assert isinstance(supa, SupabaseStyleHub)
    assert isinstance(create_style_hub(AccountSettings()), NullStyleHub)
