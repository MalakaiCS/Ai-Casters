"""Tests for the team roster / role-change client."""

from __future__ import annotations

import ai_caster.auth.team as team_mod
from ai_caster.auth.team import (
    NullTeamClient,
    SupabaseTeamClient,
    TeamMember,
    create_team_client,
)
from ai_caster.config.models import AccountProvider, AccountSettings
from ai_caster.core.http import HttpError

URL = "https://demo.supabase.co"
KEY = "anon-key"
TOKEN = "user-token"

_ROWS = [
    {"id": "u1", "email": "owner@x.com", "display_name": "Owner", "role": "owner"},
    {
        "id": "u2",
        "email": "staff@x.com",
        "display_name": "",
        "role": "staff",
        "tier": "pro",
        "tier_expires_at": "2027-01-01T00:00:00+00:00",
    },
]


def test_members_from_rows_maps_fields():
    members = SupabaseTeamClient._members_from_rows(_ROWS)
    assert [m.email for m in members] == ["owner@x.com", "staff@x.com"]
    assert members[0].role_enum.value == "owner"
    assert "staff" in members[1].label


def test_members_from_rows_ignores_garbage():
    assert SupabaseTeamClient._members_from_rows(None) == []
    assert SupabaseTeamClient._members_from_rows(["nope", 3]) == []


def test_list_members(monkeypatch):
    calls = {}

    def fake_get(url, *, headers=None, timeout=8.0):
        calls["url"] = url
        calls["headers"] = headers
        return _ROWS

    monkeypatch.setattr(team_mod, "get_json", fake_get)
    members = SupabaseTeamClient(URL, KEY).list_members(token=TOKEN)
    assert len(members) == 2
    assert "/rest/v1/profiles" in calls["url"]
    assert calls["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_set_role_posts_to_rpc(monkeypatch):
    calls = {}

    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        calls["url"] = url
        calls["payload"] = payload
        return {}

    monkeypatch.setattr(team_mod, "post_json", fake_post)
    result = SupabaseTeamClient(URL, KEY).set_role("u2", "admin", token=TOKEN)
    assert result.ok
    assert calls["url"].endswith("/rest/v1/rpc/set_user_role")
    assert calls["payload"] == {"target_user": "u2", "new_role": "admin"}


def test_members_parse_tier_and_expiry():
    members = SupabaseTeamClient._members_from_rows(_ROWS)
    assert members[0].tier == "free"  # default when absent
    assert members[0].tier_summary == "free (lifetime)"
    assert members[1].tier == "pro"
    assert members[1].tier_summary == "pro (until 2027-01-01)"


def test_set_tier_posts_to_rpc(monkeypatch):
    calls = {}

    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        calls["url"] = url
        calls["payload"] = payload
        return {}

    monkeypatch.setattr(team_mod, "post_json", fake_post)
    result = SupabaseTeamClient(URL, KEY).set_tier(
        "u2", "studio", "2027-01-01T00:00:00+00:00", token=TOKEN
    )
    assert result.ok
    assert calls["url"].endswith("/rest/v1/rpc/set_user_tier")
    assert calls["payload"] == {
        "target_user": "u2",
        "new_tier": "studio",
        "expires_at": "2027-01-01T00:00:00+00:00",
    }


def test_set_tier_lifetime_passes_null_expiry(monkeypatch):
    calls = {}

    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        calls["payload"] = payload
        return {}

    monkeypatch.setattr(team_mod, "post_json", fake_post)
    SupabaseTeamClient(URL, KEY).set_tier("u2", "pro", None, token=TOKEN)
    assert calls["payload"]["expires_at"] is None


def test_set_role_forbidden_is_friendly(monkeypatch):
    def fake_post(url, payload=None, *, headers=None, timeout=8.0):
        raise HttpError("forbidden", status=403)

    monkeypatch.setattr(team_mod, "post_json", fake_post)
    result = SupabaseTeamClient(URL, KEY).set_role("u1", "owner", token=TOKEN)
    assert not result.ok
    assert "not allowed" in result.error


def test_null_client_is_unsupported():
    client = NullTeamClient()
    assert client.supported is False
    assert client.list_members(token="x") == []
    assert not client.set_role("u", "admin", token="x").ok


def test_factory_selects_supabase_or_null():
    supa = create_team_client(
        AccountSettings(provider=AccountProvider.SUPABASE, supabase_url=URL, supabase_anon_key=KEY)
    )
    assert isinstance(supa, SupabaseTeamClient)
    assert isinstance(create_team_client(AccountSettings()), NullTeamClient)


def test_team_member_label_prefers_display_name():
    m = TeamMember("u", "e@x.com", "Kai", "admin")
    assert m.label.startswith("Kai — admin")
