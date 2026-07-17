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


def test_offline_signup_creates_session():
    backend = OfflineAuthBackend()
    result = backend.signup("new@example.com", "pw", device_id=DEVICE)
    assert result.ok and result.session is not None
    assert result.session.account.email == "new@example.com"


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


def test_session_store_persists_role(tmp_path: Path):
    # Regression: a restored session (e.g. after an auto-update restart) must keep
    # the real RBAC role instead of silently defaulting to "user".
    store = SessionStore(tmp_path / "session.json")
    session = AuthSession(
        account=Account(user_id="u1", email="a@b.c", role="admin", tier="pro"),
        access_token="tok",
    )
    store.save(session)
    loaded = store.load()
    assert loaded is not None
    assert loaded.account.role == "admin"


def test_client_restore_keeps_role(tmp_path: Path):
    # A non-expired restored session should surface the persisted role to the app.
    store = SessionStore(tmp_path / "session.json")
    store.save(
        AuthSession(
            account=Account(user_id="u1", email="a@b.c", role="owner"),
            access_token="tok",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    )
    client = AuthClient(
        EventBus(), OfflineAuthBackend(), device_id="dev", store=store, remember=True
    )
    assert client.restore() is True
    assert client.account is not None
    assert client.account.role == "owner"
    assert client.account.role_enum.value == "owner"


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


def test_client_signup_signs_in_offline(tmp_path: Path):
    bus = EventBus()
    events: list[AuthStateChanged] = []
    bus.subscribe(AuthStateChanged, events.append)
    client = _client(tmp_path, bus)
    result = client.signup("fresh@example.com", "password123")
    assert result.ok and result.session is not None
    assert client.is_authenticated
    assert events and events[-1].authenticated


class _ConfirmBackend(OfflineAuthBackend):
    """Signup that requires confirmation (ok, but no session yet)."""

    def signup(self, email, password, *, device_id):  # type: ignore[override]
        from ai_caster.auth.models import AuthResult

        return AuthResult(ok=True, session=None)


def test_client_signup_confirmation_required_does_not_sign_in(tmp_path: Path):
    bus = EventBus()
    client = AuthClient(bus, _ConfirmBackend(), device_id=DEVICE)
    result = client.signup("fresh@example.com", "password123")
    assert result.ok and result.session is None
    assert not client.is_authenticated  # must wait for email confirmation


def test_refresh_role_updates_and_republishes(tmp_path: Path):
    # A backend that reports a fresher role than the restored session carries.
    class _RoleBackend(OfflineAuthBackend):
        def with_role(self, session):
            from dataclasses import replace

            return replace(session, account=replace(session.account, role="admin"))

    bus = EventBus()
    events: list = []
    bus.subscribe(AuthStateChanged, events.append)
    store = SessionStore(tmp_path / "s.json")
    store.save(
        AuthSession(
            account=Account(user_id="u1", email="a@b.c", role="user"),
            access_token="tok",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    )
    client = AuthClient(bus, _RoleBackend(), device_id="d", store=store, remember=True)
    assert client.restore()
    assert client.account.role == "user"  # stale role from the store
    assert client.refresh_role() is True
    assert client.account.role == "admin"  # corrected from the backend
    # Re-saved with the corrected role, so the next restart is right too.
    assert store.load().account.role == "admin"
    assert any(e.authenticated and e.detail == "role refreshed" for e in events)


def test_refresh_role_noop_without_backend_support(tmp_path: Path):
    # OfflineAuthBackend has no with_role -> refresh_role is a harmless no-op.
    store = SessionStore(tmp_path / "s.json")
    store.save(
        AuthSession(
            account=Account(user_id="u1", email="a@b.c", role="owner"),
            access_token="tok",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    )
    client = AuthClient(
        EventBus(), OfflineAuthBackend(), device_id="d", store=store, remember=True
    )
    client.restore()
    assert client.refresh_role() is False
    assert client.account.role == "owner"
