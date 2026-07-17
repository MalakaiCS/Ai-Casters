"""Account and session models for the authentication client (Module 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_caster.auth.roles import Role


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Account:
    """An authenticated user account.

    ``tier`` is the subscription tier *name* reported by the account service; the
    licensing client is authoritative for what that tier actually unlocks. ``role``
    is the RBAC role name (``owner``/``founder``/``admin``/``staff``/``partner``/
    ``user``); it defaults to ``user`` and is authoritative for in-app permissions
    (see :mod:`ai_caster.auth.roles`).
    """

    user_id: str
    email: str
    display_name: str = ""
    tier: str = "free"
    role: str = "user"

    @property
    def label(self) -> str:
        return self.display_name or self.email or self.user_id

    @property
    def role_enum(self) -> Role:
        return Role.coerce(self.role)


@dataclass(frozen=True)
class AuthSession:
    """A logged-in session: the account plus its (opaque) tokens.

    ``expires_at`` is when ``access_token`` stops being accepted; a session past
    that point should be refreshed before use.
    """

    account: Account
    access_token: str
    refresh_token: str = ""
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or _utcnow()) >= self.expires_at


@dataclass(frozen=True)
class AuthResult:
    """The outcome of a login/refresh attempt."""

    ok: bool
    session: AuthSession | None = None
    error: str = ""
