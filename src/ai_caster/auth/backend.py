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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from ai_caster.auth.models import Account, AuthResult, AuthSession
from ai_caster.core.http import HttpError, get_json, post_json
from ai_caster.core.logging import get_logger

_log = get_logger("auth.backend")


@runtime_checkable
class AuthBackend(Protocol):
    """Authenticates credentials, registers accounts, and refreshes sessions."""

    @property
    def name(self) -> str: ...

    def login(self, email: str, password: str, *, device_id: str) -> AuthResult: ...

    def signup(self, email: str, password: str, *, device_id: str) -> AuthResult: ...

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult: ...

    def logout(self, session: AuthSession) -> None: ...

    def recover(self, email: str) -> AuthResult: ...


class UnconfiguredAuthBackend:
    """A backend for builds where no real account service is configured.

    Accounts are Supabase-only in a shipped build. When the Supabase URL/key are
    missing (e.g. a build made without the deployment secrets), we refuse every
    sign-in with a clear message rather than silently accepting anything. This is
    the safe default: no credential is ever treated as valid.
    """

    name = "unconfigured"

    _MESSAGE = (
        "Accounts aren't set up for this build. Sign-in requires the app to be "
        "configured with its account service."
    )

    def login(self, email: str, password: str, *, device_id: str) -> AuthResult:
        return AuthResult(ok=False, error=self._MESSAGE)

    def signup(self, email: str, password: str, *, device_id: str) -> AuthResult:
        return AuthResult(ok=False, error=self._MESSAGE)

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult:
        return AuthResult(ok=False, error=self._MESSAGE)

    def logout(self, session: AuthSession) -> None:
        return None

    def recover(self, email: str) -> AuthResult:
        return AuthResult(ok=False, error=self._MESSAGE)


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

    def signup(self, email: str, password: str, *, device_id: str) -> AuthResult:
        # Offline there is no registration step; creating an account is the same
        # deterministic mapping as signing in.
        return self.login(email, password, device_id=device_id)

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult:
        # Offline sessions never expire server-side; a refresh just mints a fresh
        # window for the same account.
        if not session.account.email:
            return AuthResult(ok=False, error="Nothing to refresh.")
        return AuthResult(ok=True, session=self._session(session.account.email, device_id))

    def logout(self, session: AuthSession) -> None:  # noqa: D401 - no server state to clear
        return None

    def recover(self, email: str) -> AuthResult:
        # Offline there is no email to send; accept so the UI flow completes.
        if not email:
            return AuthResult(ok=False, error="Enter your email address.")
        return AuthResult(ok=True)


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

    def signup(self, email: str, password: str, *, device_id: str) -> AuthResult:
        try:  # pragma: no cover - needs a live server
            data = post_json(
                f"{self._base}/auth/signup",
                {"email": email, "password": password, "device_id": device_id},
                timeout=self._timeout,
            )
            return self._parse(data)
        except HttpError as exc:  # pragma: no cover - network failure path
            _log.warning("Sign-up failed: %s", exc)
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

    def recover(self, email: str) -> AuthResult:
        try:  # pragma: no cover - needs a live server
            post_json(f"{self._base}/auth/recover", {"email": email}, timeout=self._timeout)
            return AuthResult(ok=True)
        except HttpError as exc:  # pragma: no cover - network failure path
            return AuthResult(ok=False, error=str(exc))


class SupabaseAuthBackend:
    """Authenticates against Supabase Auth (GoTrue) over its REST API.

    Uses the project URL and the **anon** public key (safe to ship in a desktop
    app — access is governed by Row Level Security on the database side; the
    service-role key must never be embedded). Talks to the standard GoTrue
    endpoints: ``/token`` (password + refresh grants), ``/signup`` and ``/logout``.
    The request/response shaping is factored into small pure helpers so the whole
    backend is unit-tested without a network.
    """

    name = "supabase"

    def __init__(self, url: str, anon_key: str, *, timeout: float = 8.0) -> None:
        base = url.rstrip("/")
        self._auth = base + "/auth/v1"
        self._rest = base + "/rest/v1"
        self._anon_key = anon_key
        self._timeout = timeout

    # -- pure helpers --------------------------------------------------- #
    def _headers(self, token: str | None = None) -> dict[str, str]:
        bearer = token or self._anon_key
        return {"apikey": self._anon_key, "Authorization": f"Bearer {bearer}"}

    @staticmethod
    def _account_from_user(user: dict) -> Account:
        meta = user.get("user_metadata") or {}
        app_meta = user.get("app_metadata") or {}
        email = str(user.get("email", ""))
        display = str(
            meta.get("name") or meta.get("full_name") or (email.split("@", 1)[0] if email else "")
        )
        tier = str(meta.get("tier") or app_meta.get("tier") or "free")
        return Account(
            user_id=str(user.get("id", "")), email=email, display_name=display, tier=tier
        )

    def _session_from_token(self, data: dict) -> AuthSession | None:
        token = data.get("access_token")
        if not token:
            return None
        user = data.get("user") or {}
        expires_at = data.get("expires_at")
        if expires_at is not None:
            expiry = datetime.fromtimestamp(int(expires_at), tz=UTC)
        else:
            expiry = datetime.now(UTC) + timedelta(seconds=int(data.get("expires_in", 3600)))
        return AuthSession(
            account=self._account_from_user(user),
            access_token=str(token),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=expiry,
        )

    @staticmethod
    def _friendly(exc: HttpError, *, signup: bool = False) -> str:
        if exc.status in (400, 401):
            return "Invalid email or password."
        if exc.status == 422 and signup:
            return "That email is already registered."
        if exc.status == 429:
            return "Too many attempts; please wait a moment and try again."
        return f"Authentication service error ({exc.status or 'network'})."

    @staticmethod
    def _parse_role(rows: object) -> str:
        """Pull the ``role`` string out of a PostgREST ``profiles`` response."""
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return str(rows[0].get("role") or "user")
        if isinstance(rows, dict):  # single-object response shape
            return str(rows.get("role") or "user")
        return "user"

    def _fetch_role(self, session: AuthSession) -> str:  # pragma: no cover - needs a server
        """Read the signed-in user's role from the ``profiles`` table.

        RLS lets a user read only their own row. Any failure (no table yet, RLS,
        network) degrades to the default ``user`` role so sign-in still succeeds.
        """
        try:
            rows = get_json(
                f"{self._rest}/profiles?id=eq.{session.account.user_id}&select=role",
                headers=self._headers(session.access_token),
                timeout=self._timeout,
            )
        except HttpError:
            return "user"
        return self._parse_role(rows)

    def _with_role(self, session: AuthSession) -> AuthSession:
        """Return ``session`` with the account's role populated from the DB."""
        role = self._fetch_role(session)
        if role == session.account.role:
            return session
        account = replace(session.account, role=role)
        return replace(session, account=account)

    # -- backend interface ---------------------------------------------- #
    def login(self, email: str, password: str, *, device_id: str) -> AuthResult:
        if not email or not password:
            return AuthResult(ok=False, error="Email and password are required.")
        try:
            data = post_json(
                f"{self._auth}/token?grant_type=password",
                {"email": email, "password": password},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except HttpError as exc:
            return AuthResult(ok=False, error=self._friendly(exc))
        session = self._session_from_token(data)
        if session is None:
            return AuthResult(ok=False, error="Invalid email or password.")
        return AuthResult(ok=True, session=self._with_role(session))

    def signup(self, email: str, password: str, *, device_id: str) -> AuthResult:
        if not email or not password:
            return AuthResult(ok=False, error="Email and password are required.")
        try:
            data = post_json(
                f"{self._auth}/signup",
                {"email": email, "password": password},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except HttpError as exc:
            return AuthResult(ok=False, error=self._friendly(exc, signup=True))
        session = self._session_from_token(data)
        if session is not None:
            # Auto-confirmed: signed in. A brand-new account is role "user" until
            # an Owner/Admin elevates it, so no role fetch is needed here.
            return AuthResult(ok=True, session=session)
        # No token but a user was created -> email confirmation is required.
        if data.get("id") or data.get("user"):
            return AuthResult(ok=True, session=None)
        return AuthResult(ok=False, error="Sign-up failed.")

    def refresh(self, session: AuthSession, *, device_id: str) -> AuthResult:
        if not session.refresh_token:
            return AuthResult(ok=False, error="No refresh token.")
        try:
            data = post_json(
                f"{self._auth}/token?grant_type=refresh_token",
                {"refresh_token": session.refresh_token},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except HttpError as exc:
            return AuthResult(ok=False, error=self._friendly(exc))
        refreshed = self._session_from_token(data)
        if refreshed is None:
            return AuthResult(ok=False, error="Could not refresh session.")
        return AuthResult(ok=True, session=self._with_role(refreshed))

    def logout(self, session: AuthSession) -> None:
        try:
            post_json(
                f"{self._auth}/logout",
                {},
                headers=self._headers(session.access_token),
                timeout=self._timeout,
            )
        except HttpError:  # best effort — local sign-out still proceeds
            pass

    def recover(self, email: str) -> AuthResult:
        """Trigger Supabase's password-recovery email (GoTrue ``/recover``)."""
        if not email:
            return AuthResult(ok=False, error="Enter your email address.")
        try:
            post_json(
                f"{self._auth}/recover",
                {"email": email},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except HttpError as exc:
            # Don't reveal whether the address exists; only surface rate limits.
            if exc.status == 429:
                return AuthResult(ok=False, error=self._friendly(exc))
            return AuthResult(ok=True)
        return AuthResult(ok=True)
