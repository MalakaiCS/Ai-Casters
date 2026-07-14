"""Tests for the authentication client, offline backend and session store."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_caster.auth.backend import OfflineAuthBackend
from ai_caster.auth.client import AuthClient
from ai_caster.auth.events import AuthStateChanged
from ai_caster.auth.models import Account, AuthSession
from ai_caster.auth.store import SessionStore
from ai_caster.core.events import EventBus

DEVICE = "device-abc"


# --- offline backend ------------------------------------------------------- #
def test_offline_login_is_deterministic():
    backend = OfflineAuthBackend()
    a = backend.login("caster@example.com", "pw", device_id=DEVICE)
    b = backend.login("caster@example.com", "pw", device_id=DEVICE)
    assert a.ok and b.ok
    assert a.session.account == b.session.account
    assert a.session.access_token == b.session.access_token


def test_offline_login_rejects_empty_credentials():
    backend = OfflineAuthBackend()
    assert not backend.login("", "pw", device_id=DEVICE).ok
    assert not backend.login("a@b.c", "", device_id=DEVICE).ok


def test_offline_refresh_mints_new_window():
    backend = OfflineAuthBackend(session_ttl=timedelta(days=1))
    session = backend.login("a@b.c", "pw", device_id=DEVICE).session
    refreshed = backend.refresh(session, device_id=DEVICE)
    assert refreshed.ok
    assert refreshed.session.account == session.account


# --- session store --------------------------------------------------------- #
def test_session_store_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path / "session.json")
    assert store.load() is None
    session = AuthSession(
        account=Account(user_id="u1", email="a@b.c", display_name="A", tier="pro"),
        access_token="tok",
        refresh_token="ref",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    store.save(session)
    loaded = store.load()
    assert loaded is not None
    assert loaded.account.user_id == "u1"
    assert loaded.access_token == "tok"
    assert loaded.expires_at == session.expires_at
    store.clear()
    assert store.load() is None


def test_session_store_ignores_corrupt_file(tmp_path: Path):
    path = tmp_path / "session.json"
    path.write_text("{ broken", encoding="utf-8")
    assert SessionStore(path).load() is None


# --- client ---------------------------------------------------------------- #
def _client(tmp_path: Path, bus: EventBus, **kwargs) -> AuthClient:
    return AuthClient(
        bus,
        OfflineAuthBackend(),
        device_id=DEVICE,
        store=SessionStore(tmp_path / "session.json"),
        **kwargs,
    )


def test_client_login_publishes_and_persists(tmp_path: Path):
    bus = EventBus()
    events: list[AuthStateChanged] = []
    bus.subscribe(AuthStateChanged, events.append)
    client = _client(tmp_path, bus)

    assert client.login("caster@example.com", "pw")
    assert client.is_authenticated
    assert client.account.email == "caster@example.com"
    assert events and events[-1].authenticated
    # Session persisted for "remember me".
    assert (tmp_path / "session.json").exists()


def test_client_login_failure_publishes_signed_out(tmp_path: Path):
    bus = EventBus()
    events: list[AuthStateChanged] = []
    bus.subscribe(AuthStateChanged, events.append)
    client = _client(tmp_path, bus)
    assert not client.login("", "")
    assert not client.is_authenticated
    assert events and not events[-1].authenticated


def test_client_restore_reuses_saved_session(tmp_path: Path):
    bus = EventBus()
    _client(tmp_path, bus).login("caster@example.com", "pw")
    # A fresh client restores the persisted session without a new login.
    fresh = _client(tmp_path, bus)
    assert fresh.restore()
    assert fresh.account.email == "caster@example.com"


def test_client_restore_refreshes_expired_session(tmp_path: Path):
    bus = EventBus()
    store = SessionStore(tmp_path / "session.json")
    expired = AuthSession(
        account=Account(user_id="u1", email="a@b.c", display_name="A"),
        access_token="old",
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    store.save(expired)
    client = AuthClient(bus, OfflineAuthBackend(), device_id=DEVICE, store=store)
    assert client.restore()  # offline backend re-mints from the account
    assert client.account.email == "a@b.c"
    assert not client.session.is_expired()


def test_client_logout_clears_session(tmp_path: Path):
    bus = EventBus()
    client = _client(tmp_path, bus)
    client.login("caster@example.com", "pw")
    client.logout()
    assert not client.is_authenticated
    assert not (tmp_path / "session.json").exists()


def test_remember_false_does_not_persist(tmp_path: Path):
    bus = EventBus()
    client = _client(tmp_path, bus, remember=False)
    client.login("caster@example.com", "pw")
    assert client.is_authenticated
    assert not (tmp_path / "session.json").exists()
