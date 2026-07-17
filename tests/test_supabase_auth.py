"""Tests for the Supabase auth backend and the auth-backend factory.

Supabase's REST transport is monkeypatched, so these exercise the real request
shaping and response parsing without any network.
"""

from __future__ import annotations

import ai_caster.auth.backend as backend_mod
from ai_caster.auth.backend import (
    HttpAuthBackend,
    OfflineAuthBackend,
    SupabaseAuthBackend,
    UnconfiguredAuthBackend,
)
from ai_caster.auth.factory import create_auth_backend
from ai_caster.config.models import AccountProvider, AccountSettings
from ai_caster.core.http import HttpError

URL = "https://demo.supabase.co"
KEY = "anon-key-123"
DEVICE = "dev-1"

_USER = {
    "id": "uuid-1",
    "email": "caster@example.com",
    "user_metadata": {"name": "Kai", "tier": "pro"},
}


def _backend() -> SupabaseAuthBackend:
    return SupabaseAuthBackend(URL, KEY)


class _FakeTransport:
    """Stands in for core.http.post_json; records calls and returns canned data."""

    def __init__(self, response=None, error: HttpError | None = None) -> None:
        self.response = response if response is not None else {}
        self.error = error
        self.calls: list[tuple] = []

    def __call__(self, url, payload=None, *, headers=None, timeout=8.0):
        self.calls.append((url, payload, headers))
        if self.error is not None:
            raise self.error
        return self.response


# --- pure helpers ---------------------------------------------------------- #
def test_url_and_key_whitespace_is_stripped():
    # A trailing newline/space (common in pasted CI secrets) must not reach the
    # hostname, or DNS fails with getaddrinfo.
    b = SupabaseAuthBackend("https://demo.supabase.co\n ", "  anon-key\n")
    assert b._auth == "https://demo.supabase.co/auth/v1"
    assert b._anon_key == "anon-key"


def test_headers_include_apikey_and_bearer():
    b = _backend()
    headers = b._headers()
    assert headers["apikey"] == KEY
    assert headers["Authorization"] == f"Bearer {KEY}"
    # A user token overrides the bearer.
    assert b._headers("user-tok")["Authorization"] == "Bearer user-tok"


def test_account_from_user_maps_fields():
    account = SupabaseAuthBackend._account_from_user(_USER)
    assert account.user_id == "uuid-1"
    assert account.email == "caster@example.com"
    assert account.display_name == "Kai"
    assert account.tier == "pro"


def test_account_display_falls_back_to_email_local_part():
    account = SupabaseAuthBackend._account_from_user({"id": "x", "email": "abc@d.com"})
    assert account.display_name == "abc"
    assert account.tier == "free"


def test_session_from_token_none_without_access_token():
    assert _backend()._session_from_token({"user": _USER}) is None


def test_session_from_token_builds_session():
    session = _backend()._session_from_token(
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "user": _USER}
    )
    assert session is not None
    assert session.access_token == "at"
    assert session.refresh_token == "rt"
    assert not session.is_expired()
    assert session.account.tier == "pro"


def _fake_role(role="user"):
    """A fake core.http.get_json returning a PostgREST profiles row."""

    def _get(url, *, headers=None, timeout=8.0):
        return [{"role": role}]

    return _get


# --- login ----------------------------------------------------------------- #
def test_login_success(monkeypatch):
    fake = _FakeTransport({"access_token": "at", "refresh_token": "rt", "user": _USER})
    monkeypatch.setattr(backend_mod, "post_json", fake)
    monkeypatch.setattr(backend_mod, "get_json", _fake_role("staff"))
    result = _backend().login("caster@example.com", "pw", device_id=DEVICE)
    assert result.ok and result.session is not None
    assert result.session.account.email == "caster@example.com"
    # The role is pulled from the profiles table and applied to the account.
    assert result.session.account.role == "staff"
    # Hit the password-grant endpoint with the anon apikey.
    url, payload, headers = fake.calls[0]
    assert url.endswith("/auth/v1/token?grant_type=password")
    assert payload == {"email": "caster@example.com", "password": "pw"}
    assert headers["apikey"] == KEY


def test_login_role_defaults_to_user_when_profile_unavailable(monkeypatch):
    fake = _FakeTransport({"access_token": "at", "refresh_token": "rt", "user": _USER})
    monkeypatch.setattr(backend_mod, "post_json", fake)

    def _boom(url, *, headers=None, timeout=8.0):
        raise HttpError("no profiles table", status=404)

    monkeypatch.setattr(backend_mod, "get_json", _boom)
    result = _backend().login("caster@example.com", "pw", device_id=DEVICE)
    assert result.ok and result.session.account.role == "user"


def test_parse_role_handles_shapes():
    assert SupabaseAuthBackend._parse_role([{"role": "admin"}]) == "admin"
    assert SupabaseAuthBackend._parse_role({"role": "owner"}) == "owner"
    assert SupabaseAuthBackend._parse_role([]) == "user"
    assert SupabaseAuthBackend._parse_role(None) == "user"


def test_login_rejects_empty_credentials():
    assert not _backend().login("", "", device_id=DEVICE).ok


def test_login_bad_credentials_is_friendly(monkeypatch):
    fake = _FakeTransport(error=HttpError("bad", status=400))
    monkeypatch.setattr(backend_mod, "post_json", fake)
    result = _backend().login("caster@example.com", "wrong", device_id=DEVICE)
    assert not result.ok
    assert "Invalid email or password" in result.error


def test_network_failure_surfaces_the_real_reason(monkeypatch):
    # A connection-level failure (status None) should report the underlying
    # reason (e.g. a TLS error) instead of a bare "network".
    err = HttpError("boom", reason="certificate verify failed")
    fake = _FakeTransport(error=err)
    monkeypatch.setattr(backend_mod, "post_json", fake)
    result = _backend().signup("caster@example.com", "password123", device_id=DEVICE)
    assert not result.ok
    assert "certificate verify failed" in result.error
    assert "Couldn't reach the account service" in result.error


# --- signup ---------------------------------------------------------------- #
def test_signup_auto_confirmed_returns_session(monkeypatch):
    fake = _FakeTransport({"access_token": "at", "refresh_token": "rt", "user": _USER})
    monkeypatch.setattr(backend_mod, "post_json", fake)
    result = _backend().signup("caster@example.com", "pw", device_id=DEVICE)
    assert result.ok and result.session is not None
    assert fake.calls[0][0].endswith("/auth/v1/signup")


def test_signup_confirmation_required(monkeypatch):
    # GoTrue returns the created user (no token) when email confirmation is on.
    fake = _FakeTransport({"id": "uuid-1", "email": "caster@example.com"})
    monkeypatch.setattr(backend_mod, "post_json", fake)
    result = _backend().signup("caster@example.com", "pw", device_id=DEVICE)
    assert result.ok and result.session is None  # created, awaiting confirmation


def test_signup_existing_email_is_friendly(monkeypatch):
    fake = _FakeTransport(error=HttpError("exists", status=422))
    monkeypatch.setattr(backend_mod, "post_json", fake)
    result = _backend().signup("caster@example.com", "pw", device_id=DEVICE)
    assert not result.ok
    assert "already registered" in result.error


# --- refresh / logout ------------------------------------------------------ #
def test_refresh_success(monkeypatch):
    fake = _FakeTransport({"access_token": "at2", "refresh_token": "rt2", "user": _USER})
    monkeypatch.setattr(backend_mod, "post_json", fake)
    monkeypatch.setattr(backend_mod, "get_json", _fake_role("user"))
    from ai_caster.auth.models import Account, AuthSession

    session = AuthSession(
        account=Account("uuid-1", "caster@example.com"), access_token="old", refresh_token="rt"
    )
    result = _backend().refresh(session, device_id=DEVICE)
    assert result.ok and result.session.access_token == "at2"
    assert fake.calls[0][0].endswith("/auth/v1/token?grant_type=refresh_token")


def test_logout_uses_bearer_token(monkeypatch):
    fake = _FakeTransport({})
    monkeypatch.setattr(backend_mod, "post_json", fake)
    from ai_caster.auth.models import Account, AuthSession

    session = AuthSession(account=Account("uuid-1", "caster@example.com"), access_token="user-tok")
    _backend().logout(session)
    _url, _payload, headers = fake.calls[0]
    assert headers["Authorization"] == "Bearer user-tok"


# --- factory --------------------------------------------------------------- #
def test_factory_selects_supabase_when_configured():
    settings = AccountSettings(
        provider=AccountProvider.SUPABASE, supabase_url=URL, supabase_anon_key=KEY
    )
    assert isinstance(create_auth_backend(settings), SupabaseAuthBackend)


def test_factory_disables_signin_when_supabase_incomplete():
    # Supabase-only: an unconfigured Supabase build refuses sign-in (never offline).
    settings = AccountSettings(provider=AccountProvider.SUPABASE)  # no url/key
    assert isinstance(create_auth_backend(settings), UnconfiguredAuthBackend)


def test_factory_http_and_offline():
    assert isinstance(
        create_auth_backend(AccountSettings(provider=AccountProvider.HTTP, server_url="https://x")),
        HttpAuthBackend,
    )
    # A non-frozen dev/test process still gets the offline backend by default.
    assert isinstance(create_auth_backend(AccountSettings()), OfflineAuthBackend)


def test_factory_disables_signin_in_frozen_build_without_config(monkeypatch):
    # A packaged build with no account service must never accept anything.
    monkeypatch.setattr("ai_caster.auth.factory.sys.frozen", True, raising=False)
    assert isinstance(create_auth_backend(AccountSettings()), UnconfiguredAuthBackend)
