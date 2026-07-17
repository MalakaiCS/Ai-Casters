"""Cloud settings-sync backends.

Push/pull the settings document to a per-account cloud store. The default
:class:`NullSyncBackend` keeps everything local (no-op), so the app runs with no
service; the :class:`HttpSyncBackend` stores the document against the account over
JSON/HTTP. The payload is the settings JSON as produced by the settings manager.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ai_caster.core.http import HttpError, get_json, post_json
from ai_caster.core.logging import get_logger

_log = get_logger("sync.backend")


@runtime_checkable
class SyncBackend(Protocol):
    """Stores and retrieves the settings document for an account."""

    @property
    def name(self) -> str: ...

    def push(self, account_id: str, payload: dict[str, Any], *, token: str = "") -> None: ...

    def pull(self, account_id: str, *, token: str = "") -> dict[str, Any] | None: ...


class NullSyncBackend:
    """Keeps a single in-memory copy (offline default / test double)."""

    name = "null"

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def push(self, account_id: str, payload: dict[str, Any], *, token: str = "") -> None:
        self._store[account_id] = payload

    def pull(self, account_id: str, *, token: str = "") -> dict[str, Any] | None:
        return self._store.get(account_id)


class HttpSyncBackend:
    """Stores the settings document against the account over JSON/HTTP."""

    name = "http"

    def __init__(self, base_url: str, *, timeout: float = 8.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    def push(self, account_id: str, payload: dict[str, Any], *, token: str = "") -> None:
        try:  # pragma: no cover - needs a live server
            post_json(
                f"{self._base}/settings/{account_id}",
                {"settings": payload},
                headers=self._auth_header(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - network path
            _log.warning("Settings push failed: %s", exc)

    def pull(self, account_id: str, *, token: str = "") -> dict[str, Any] | None:
        try:  # pragma: no cover - needs a live server
            data = get_json(
                f"{self._base}/settings/{account_id}",
                headers=self._auth_header(token),
                timeout=self._timeout,
            )
            settings = data.get("settings")
            return settings if isinstance(settings, dict) else None
        except HttpError as exc:  # pragma: no cover - network path
            _log.warning("Settings pull failed: %s", exc)
            return None


class SupabaseSyncBackend:
    """Stores the settings document in a Supabase ``user_settings`` table.

    One JSONB row per account (``user_id`` primary key), upserted/read via
    PostgREST with the anon key + the signed-in user's access token; Row Level
    Security keeps each user to their own row (see ``docs/SUPABASE.md``).
    """

    name = "supabase"

    def __init__(self, url: str, anon_key: str, *, timeout: float = 8.0) -> None:
        self._rest = url.rstrip("/") + "/rest/v1"
        self._anon = anon_key
        self._timeout = timeout

    def _headers(self, token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"apikey": self._anon, "Authorization": f"Bearer {token or self._anon}"}
        if extra:
            headers.update(extra)
        return headers

    def push(self, account_id: str, payload: dict[str, Any], *, token: str = "") -> None:
        try:
            post_json(
                f"{self._rest}/user_settings",
                {"user_id": account_id, "settings": payload},
                headers=self._headers(token, {"Prefer": "resolution=merge-duplicates"}),
                timeout=self._timeout,
            )
        except HttpError as exc:
            _log.warning("Settings push failed: %s", exc)

    def pull(self, account_id: str, *, token: str = "") -> dict[str, Any] | None:
        try:
            rows = get_json(
                f"{self._rest}/user_settings?user_id=eq.{account_id}&select=settings",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:
            _log.warning("Settings pull failed: %s", exc)
            return None
        if rows and isinstance(rows[0].get("settings"), dict):
            return rows[0]["settings"]
        return None
