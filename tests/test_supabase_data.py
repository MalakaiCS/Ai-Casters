"""Tests for the Supabase-backed licensing and settings-sync backends.

PostgREST is monkeypatched, so these exercise the real request shaping (RLS
headers, filters, upsert Prefer header) and parsing without any network or
database password.
"""

from __future__ import annotations

import ai_caster.licensing.backend as lic_mod
import ai_caster.sync.backend as sync_mod
from ai_caster.config.models import (
    AccountProvider,
    AccountSettings,
    LicensingSettings,
    SyncSettings,
)
from ai_caster.core.http import HttpError
from ai_caster.licensing.backend import LicensingError, SupabaseLicensingBackend
from ai_caster.licensing.factory import create_licensing_backend
from ai_caster.licensing.models import SubscriptionTier
from ai_caster.sync.backend import SupabaseSyncBackend
from ai_caster.sync.factory import create_sync_backend

URL = "https://demo.supabase.co"
KEY = "anon-key"
ACC = "uuid-user-1"
TOKEN = "user-jwt"


class _Transport:
    """Records calls; returns queued responses keyed by a URL substring."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._responses: dict[str, object] = {}
        self._errors: dict[str, HttpError] = {}

    def on(self, needle: str, response=None, error: HttpError | None = None) -> _Transport:
        if error is not None:
            self._errors[needle] = error
        else:
            self._responses[needle] = response
        return self

    def get(self, url, *, headers=None, timeout=8.0):
        return self._dispatch("GET", url, None, headers)

    def post(self, url, payload=None, *, headers=None, timeout=8.0):
        return self._dispatch("POST", url, payload, headers)

    def delete(self, url, *, headers=None, timeout=8.0):
        return self._dispatch("DELETE", url, None, headers)

    def _dispatch(self, method, url, payload, headers):
        self.calls.append((method, url, payload, headers))
        for needle, exc in self._errors.items():
            if needle in url:
                raise exc
        for needle, resp in self._responses.items():
            if needle in url:
                return resp
        return []


def _install(monkeypatch, module, transport: _Transport) -> None:
    monkeypatch.setattr(module, "get_json", transport.get)
    monkeypatch.setattr(module, "post_json", transport.post)
    if hasattr(module, "delete_json"):
        monkeypatch.setattr(module, "delete_json", transport.delete)


# --- licensing ------------------------------------------------------------- #
def _lic() -> SupabaseLicensingBackend:
    return SupabaseLicensingBackend(URL, KEY, device_name="Rig")


def test_licensing_validate_reads_tier_and_registers_device(monkeypatch):
    t = _Transport().on("profiles", [{"tier": "pro"}])
    _install(monkeypatch, lic_mod, t)
    lic = _lic().validate(ACC, "dev-1", token=TOKEN)
    assert lic.tier is SubscriptionTier.PRO
    # RLS headers present on the profiles query.
    _m, url, _p, headers = t.calls[0]
    assert "profiles?id=eq." + ACC in url
    assert headers["apikey"] == KEY and headers["Authorization"] == f"Bearer {TOKEN}"
    # Device was upserted with a merge-duplicates Prefer header.
    upsert = [c for c in t.calls if c[0] == "POST" and "devices" in c[1]][0]
    assert upsert[2]["device_id"] == "dev-1" and upsert[2]["name"] == "Rig"
    assert upsert[3]["Prefer"] == "resolution=merge-duplicates"


def test_licensing_validate_missing_profile_is_free(monkeypatch):
    t = _Transport().on("profiles", [])  # no row
    _install(monkeypatch, lic_mod, t)
    assert _lic().validate(ACC, "dev-1", token=TOKEN).tier is SubscriptionTier.FREE


def test_licensing_validate_error_raises(monkeypatch):
    t = _Transport().on("profiles", error=HttpError("boom", status=500))
    _install(monkeypatch, lic_mod, t)
    try:
        _lic().validate(ACC, "dev-1", token=TOKEN)
        raise AssertionError("expected LicensingError")
    except LicensingError:
        pass


def test_licensing_list_devices(monkeypatch):
    t = _Transport().on(
        "devices",
        [{"device_id": "a", "name": "Laptop", "last_seen": "2026-07-14T22:00:00+00:00"}],
    )
    _install(monkeypatch, lic_mod, t)
    devices = _lic().list_devices(ACC, token=TOKEN)
    assert devices[0].device_id == "a" and devices[0].name == "Laptop"
    assert devices[0].last_seen is not None


def test_licensing_deregister_device(monkeypatch):
    t = _Transport()
    _install(monkeypatch, lic_mod, t)
    _lic().deregister_device(ACC, "a", token=TOKEN)
    method, url, _p, _h = t.calls[0]
    assert method == "DELETE"
    assert "devices?user_id=eq." + ACC in url and "device_id=eq.a" in url


# --- sync ------------------------------------------------------------------ #
def test_sync_push_upserts(monkeypatch):
    t = _Transport()
    _install(monkeypatch, sync_mod, t)
    SupabaseSyncBackend(URL, KEY).push(ACC, {"gsi": {"port": 3111}}, token=TOKEN)
    method, url, payload, headers = t.calls[0]
    assert method == "POST" and url.endswith("/rest/v1/user_settings")
    assert payload == {"user_id": ACC, "settings": {"gsi": {"port": 3111}}}
    assert headers["Prefer"] == "resolution=merge-duplicates"


def test_sync_pull_returns_settings(monkeypatch):
    t = _Transport().on("user_settings", [{"settings": {"gsi": {"port": 4567}}}])
    _install(monkeypatch, sync_mod, t)
    result = SupabaseSyncBackend(URL, KEY).pull(ACC, token=TOKEN)
    assert result == {"gsi": {"port": 4567}}


def test_sync_pull_empty_is_none(monkeypatch):
    t = _Transport().on("user_settings", [])
    _install(monkeypatch, sync_mod, t)
    assert SupabaseSyncBackend(URL, KEY).pull(ACC, token=TOKEN) is None


# --- factories ------------------------------------------------------------- #
def _account_supabase() -> AccountSettings:
    return AccountSettings(
        provider=AccountProvider.SUPABASE, supabase_url=URL, supabase_anon_key=KEY
    )


def test_licensing_factory_selects_supabase():
    backend = create_licensing_backend(
        LicensingSettings(provider=AccountProvider.SUPABASE), _account_supabase()
    )
    assert isinstance(backend, SupabaseLicensingBackend)


def test_licensing_factory_falls_back_without_keys():
    backend = create_licensing_backend(
        LicensingSettings(provider=AccountProvider.SUPABASE), AccountSettings()
    )
    assert backend.name == "offline"


def test_sync_factory_selects_supabase():
    backend = create_sync_backend(
        SyncSettings(provider=AccountProvider.SUPABASE), _account_supabase()
    )
    assert isinstance(backend, SupabaseSyncBackend)


def test_sync_factory_falls_back_to_null():
    backend = create_sync_backend(
        SyncSettings(provider=AccountProvider.SUPABASE), AccountSettings()
    )
    assert backend.name == "null"
