"""User roles and the permissions they grant (Module 3, RBAC).

Roles are a strict hierarchy. A higher role has every permission of the roles
below it, so checks are expressed as "at least this rank" rather than as
membership tests. ``User`` is the default for a brand-new account; the elevated
roles are granted by an Owner/Admin (in Supabase, the ``profiles.role`` column is
the source of truth — see docs/SUPABASE.md).

Two permissions gate real product surfaces:

* :func:`can_train` — Staff and above may open the in-app AI training tools.
* :func:`can_manage_roles` — Admin and above may change other users' roles, and
  may only assign roles *below their own* (so an Admin can't mint an Owner).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """A user's role, from most to least privileged."""

    OWNER = "owner"
    FOUNDER = "founder"
    ADMIN = "admin"
    STAFF = "staff"
    PARTNER = "partner"
    USER = "user"

    @classmethod
    def coerce(cls, value: object) -> Role:
        """Best-effort parse of an arbitrary value into a Role (default USER)."""
        if isinstance(value, Role):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.USER


# Rank order: index 0 is the most privileged. Kept explicit (not enum order) so
# the hierarchy is unmistakable and reordering the enum can't silently change it.
_ORDER: tuple[Role, ...] = (
    Role.OWNER,
    Role.FOUNDER,
    Role.ADMIN,
    Role.STAFF,
    Role.PARTNER,
    Role.USER,
)
_RANK: dict[Role, int] = {role: len(_ORDER) - 1 - i for i, role in enumerate(_ORDER)}

DEFAULT_ROLE = Role.USER


def rank(role: Role | str) -> int:
    """Numeric privilege of a role — higher is more privileged (User = 0)."""
    return _RANK[Role.coerce(role)]


def at_least(role: Role | str, minimum: Role | str) -> bool:
    """True if ``role`` is at least as privileged as ``minimum``."""
    return rank(role) >= rank(minimum)


def can_train(role: Role | str) -> bool:
    """Staff and above may use the in-app AI training tools."""
    return at_least(role, Role.STAFF)


def can_manage_roles(role: Role | str) -> bool:
    """Admin and above may view the team and change other users' roles."""
    return at_least(role, Role.ADMIN)


def assignable_roles(actor: Role | str) -> list[Role]:
    """Roles ``actor`` is allowed to assign to others.

    A manager may only grant roles strictly below their own rank, so no one can
    create a peer or a superior. Returns an empty list for non-managers.
    """
    if not can_manage_roles(actor):
        return []
    actor_rank = rank(actor)
    return [r for r in _ORDER if rank(r) < actor_rank]


def can_assign(actor: Role | str, target_role: Role | str) -> bool:
    """Whether ``actor`` may grant ``target_role`` to someone."""
    return Role.coerce(target_role) in assignable_roles(actor)


def role_label(role: Role | str) -> str:
    """Human-friendly, capitalised role name (e.g. ``Play-by-play`` style)."""
    return Role.coerce(role).value.capitalize()
