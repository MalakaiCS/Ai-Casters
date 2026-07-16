"""Reading the team roster and changing members' roles.

The admin surface (Admin and above) lists everyone and can promote/demote them.
Roles live in the Supabase ``profiles`` table; a member's role is changed through
a **security-definer** RPC (``set_user_role``) that re-checks the caller's own
role server-side, so the anon key can never be used to grant a role the caller
isn't allowed to grant (see docs/SUPABASE.md for the SQL).

:class:`SupabaseTeamClient` talks to PostgREST/RPC; :class:`NullTeamClient` is the
no-op used when the app isn't backed by Supabase. Response shaping lives in small
pure helpers so it's unit-tested without a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai_caster.auth.roles import Role
from ai_caster.core.http import HttpError, get_json, post_json
from ai_caster.core.logging import get_logger

_log = get_logger("auth.team")


@dataclass(frozen=True)
class TeamMember:
    """One row of the team roster."""

    user_id: str
    email: str
    display_name: str
    role: str

    @property
    def role_enum(self) -> Role:
        return Role.coerce(self.role)

    @property
    def label(self) -> str:
        who = self.display_name or self.email or self.user_id
        return f"{who} — {self.role_enum.value}"


@dataclass(frozen=True)
class TeamResult:
    """Outcome of a role change."""

    ok: bool
    error: str = ""


@runtime_checkable
class TeamClient(Protocol):
    """Lists members and changes their roles (Admin+ only, enforced server-side)."""

    @property
    def supported(self) -> bool: ...

    def list_members(self, *, token: str) -> list[TeamMember]: ...

    def set_role(self, user_id: str, role: str, *, token: str) -> TeamResult: ...


class NullTeamClient:
    """No-op roster for builds that aren't backed by Supabase."""

    supported = False

    def list_members(self, *, token: str) -> list[TeamMember]:
        return []

    def set_role(self, user_id: str, role: str, *, token: str) -> TeamResult:
        return TeamResult(ok=False, error="Team management needs the cloud account service.")


class SupabaseTeamClient:
    """Reads/writes roles via Supabase PostgREST and the set_user_role RPC."""

    supported = True

    def __init__(self, url: str, anon_key: str, *, timeout: float = 8.0) -> None:
        self._rest = url.strip().rstrip("/") + "/rest/v1"
        self._anon_key = anon_key.strip()
        self._timeout = timeout

    def _headers(self, token: str) -> dict[str, str]:
        return {"apikey": self._anon_key, "Authorization": f"Bearer {token or self._anon_key}"}

    @staticmethod
    def _members_from_rows(rows: object) -> list[TeamMember]:
        if not isinstance(rows, list):
            return []
        members: list[TeamMember] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            members.append(
                TeamMember(
                    user_id=str(row.get("id", "")),
                    email=str(row.get("email", "")),
                    display_name=str(row.get("display_name") or ""),
                    role=str(row.get("role") or "user"),
                )
            )
        return members

    def list_members(self, *, token: str) -> list[TeamMember]:
        try:
            rows = get_json(
                f"{self._rest}/profiles?select=id,email,display_name,role&order=role.asc",
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - network failure path
            _log.warning("Could not list team members: %s", exc)
            return []
        return self._members_from_rows(rows)

    def set_role(self, user_id: str, role: str, *, token: str) -> TeamResult:
        role_value = Role.coerce(role).value
        try:
            post_json(
                f"{self._rest}/rpc/set_user_role",
                {"target_user": user_id, "new_role": role_value},
                headers=self._headers(token),
                timeout=self._timeout,
            )
        except HttpError as exc:  # pragma: no cover - network failure path
            if exc.status in (401, 403):
                return TeamResult(ok=False, error="You're not allowed to set that role.")
            return TeamResult(ok=False, error=f"Role change failed ({exc.status or 'network'}).")
        return TeamResult(ok=True)


def create_team_client(account_settings) -> TeamClient:  # noqa: ANN001 - AccountSettings
    """Build the team client for the configured account provider."""
    from ai_caster.config.models import AccountProvider

    if (
        account_settings.provider is AccountProvider.SUPABASE
        and account_settings.supabase_url
        and account_settings.supabase_anon_key
    ):
        return SupabaseTeamClient(account_settings.supabase_url, account_settings.supabase_anon_key)
    return NullTeamClient()
