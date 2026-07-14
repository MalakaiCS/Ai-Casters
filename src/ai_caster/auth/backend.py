"""Authentication backends.

The backend is the seam between the app and an account service. The default
:class:`OfflineAuthBackend` authenticates entirely locally, so the whole product
runs, is demoed and is tested with no server and no network. The
:class:`HttpAuthBackend` talks to a real service over JSON/HTTP for production
sign-in. Both satisfy the same :class:`AuthBackend` interface, so the
:class:`~ai_caster.auth.client.AuthClient` never knows which it has.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from ai_caster.auth.models import Account, AuthResult, AuthSession
from ai_caster.core.http import HttpError, post_json
from ai_caster.core.logging import get_logger

_log = get_logger("auth.backend")


@runtime_checkable
class AuthBackend(Protocol):
    """Authenticates credentials and refreshes sessions."""

    @property
    def name(self) -> str: ...

    def login(self, email: str, password: str, *, device_id: str) -> AuthResult: ...

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult: ...

    def logout(self, session: AuthSession) -> None: ...


class OfflineAuthBackend:
    """Deterministic local authentication — no server, no network.

    Any non-empty email/password is accepted and mapped to a stable local
    account (the user id is derived from the email so the same login always
    yields the same account). This is the default backend: it makes the account
    surface fully usable offline and completely deterministic under test. It is
    explicitly *not* a security boundary — a real deployment configures the HTTP
    backend against an account service.
    """

    name = "offline"

    def __init__(self, *, session_ttl: timedelta = timedelta(days=7)) -> None:
        self._ttl = session_ttl

    def _account(self, email: str) -> Account:
        user_id = "local-" + hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:16]
        display = email.split("@", 1)[0] if "@" in email else email
        return Account(user_id=user_id, email=email, display_name=display, tier="free")

    def _session(self, email: str, device_id: str) -> AuthSession:
        account = self._account(email)
        seed = f"{account.user_id}:{device_id}".encode()
        token = hashlib.sha256(seed).hexdigest()
        return AuthSession(
            account=account,
            access_token=token,
            refresh_token=token[::-1],
            expires_at=datetime.now(UTC) + self._ttl,
        )

    def login(self, email: str, password: str, *, device_id: str) -> AuthResult:
        if not email or not password:
            return AuthResult(ok=False, error="Email and password are required.")
        return AuthResult(ok=True, session=self._session(email, device_id))

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult:
        # Offline sessions never expire server-side; a refresh just mints a fresh
        # window for the same account.
        if not session.account.email:
            return AuthResult(ok=False, error="Nothing to refresh.")
        return AuthResult(ok=True, session=self._session(session.account.email, device_id))

    def logout(self, session: AuthSession) -> None:  # noqa: D401 - no server state to clear
        return None


class HttpAuthBackend:
    """Authenticates against a real account service over JSON/HTTP."""

    name = "http"

    def __init__(self, base_url: str, *, timeout: float = 8.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _parse(self, data: dict) -> AuthResult:  # pragma: no cover - needs a live server
        account_data = data.get("account", {})
        account = Account(
            user_id=str(account_data.get("user_id", "")),
            email=str(account_data.get("email", "")),
            display_name=str(account_data.get("display_name", "")),
            tier=str(account_data.get("tier", "free")),
        )
        expires = data.get("expires_at")
        expires_at = datetime.fromisoformat(expires) if expires else None
        session = AuthSession(
            account=account,
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=expires_at,
        )
        return AuthResult(ok=bool(session.access_token), session=session)

    def login(self, email: str, password: str, *, device_id: str) -> AuthResult:
        try:  # pragma: no cover - needs a live server
            data = post_json(
                f"{self._base}/auth/login",
                {"email": email, "password": password, "device_id": device_id},
                timeout=self._timeout,
            )
            return self._parse(data)
        except HttpError as exc:  # pragma: no cover - network failure path
            _log.warning("Login failed: %s", exc)
            return AuthResult(ok=False, error=str(exc))

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult:
        try:  # pragma: no cover - needs a live server
            data = post_json(
                f"{self._base}/auth/refresh",
                {"refresh_token": session.refresh_token, "device_id": device_id},
                timeout=self._timeout,
            )
            return self._parse(data)
        except HttpError as exc:  # pragma: no cover - network failure path
            return AuthResult(ok=False, error=str(exc))

    def logout(self, session: AuthSession) -> None:
        try:  # pragma: no cover - needs a live server
            post_json(
                f"{self._base}/auth/logout",
                {"access_token": session.access_token},
                timeout=self._timeout,
            )
        except HttpError:  # pragma: no cover - best effort
            pass
