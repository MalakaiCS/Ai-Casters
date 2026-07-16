"""The shared style hub — one trained style everyone casts with.

Training is done by Staff, but its value is shared: a trained
:class:`~ai_caster.training.models.StyleProfile` is **published to a central hub**
(a Supabase table) and **every app pulls the latest one on launch**, so any user
can cast with the team's trained style immediately — no local training needed.

* :class:`SupabaseStyleHub` reads/writes the ``style_hub`` table over PostgREST
  (RLS: everyone signed-in may read the latest; only Staff+ may publish — see
  ``docs/SUPABASE.md``).
* :class:`NullStyleHub` is the no-op used when the app isn't Supabase-backed.

Response shaping is a couple of pure helpers so it's unit-tested without a
network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai_caster.core.http import HttpError, get_json, post_json
from ai_caster.core.logging import get_logger
from ai_caster.training.models import StyleProfile

_log = get_logger("training.hub")


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class SharedProfile:
    """A profile pulled from the hub, with a little publish metadata."""

    profile: StyleProfile
    summary: str = ""
    published_at: str = ""


@runtime_checkable
class StyleHub(Protocol):
    """Publishes and fetches the shared style profile."""

    @property
    def supported(self) -> bool: ...

    def fetch_latest(self, *, token: str) -> SharedProfile | None: ...

    def publish(self, profile: StyleProfile, summary: str, *, token: str) -> PublishResult: ...


class NullStyleHub:
    """No-op hub for builds that aren't backed by Supabase."""

    supported = False

    def fetch_latest(self, *, token: str) -> SharedProfile | None:
        return None

    def publish(self, profile: StyleProfile, summary: str, *, token: str) -> PublishResult:
        return PublishResult(ok=False, error="The shared hub needs the cloud account service.")


class SupabaseStyleHub:
    """Shared style profiles via the Supabase ``style_hub`` table."""

    supported = True

    def __init__(self, url: str, anon_key: str, *, timeout: float = 8.0) -> None:
        self._rest = url.strip().rstrip("/") + "/rest/v1"
        self._anon_key = anon_key.strip()
        self._timeout = timeout

    def _headers(self, token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {token or self._anon_key}",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _shared_from_row(rows: object) -> SharedProfile | None:
        row = None
        if isinstance(rows, list) and rows:
            row = rows[0]
        elif isinstance(rows, dict):
            row = rows
        if not isinstance(row, dict):
            return None
        raw = row.get("profile")
        if not isinstance(raw, dict):
            return None
        return SharedProfile(
            profile=StyleProfile.from_dict(raw),
            summary=str(row.get("summary") or ""),
            published_at=str(row.get("published_at") or ""),
        )

    def fetch_latest(self, *, token: str) -> SharedProfile | None:
        try:
            rows = get_json(
                f"{self._rest}/style_hub?select=profile,summary,published_at"
                "&order=published_at.desc&limit=1",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - network failure path
            _log.info("Could not fetch shared style: %s", exc)
            return None
        return self._shared_from_row(rows)

    def publish(self, profile: StyleProfile, summary: str, *, token: str) -> PublishResult:
        try:
            post_json(
                f"{self._rest}/style_hub",
                {"profile": profile.to_dict(), "summary": summary},
                headers=self._headers(token, {"Prefer": "return=minimal"}),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - network failure path
            if exc.status in (401, 403):
                return PublishResult(ok=False, error="Only Staff and above can publish.")
            return PublishResult(ok=False, error=f"Publish failed ({exc.status or 'network'}).")
        return PublishResult(ok=True)


def create_style_hub(account_settings) -> StyleHub:  # noqa: ANN001 - AccountSettings
    """Build the shared-style hub for the configured account provider."""
    from ai_caster.config.models import AccountProvider

    if (
        account_settings.provider is AccountProvider.SUPABASE
        and account_settings.supabase_url
        and account_settings.supabase_anon_key
    ):
        return SupabaseStyleHub(account_settings.supabase_url, account_settings.supabase_anon_key)
    return NullStyleHub()
