"""Module 3 — Authentication Client.

Sign-in/sign-up/out and session management behind an :class:`AuthBackend`
interface. The default backend authenticates locally (offline, deterministic, no
server), so the account surface is fully usable and testable without a backend;
:class:`SupabaseAuthBackend` uses Supabase Auth (GoTrue) and an HTTP backend a
custom service. The client persists the session for "remember me" and announces
sign-in state on the event bus.
"""

from ai_caster.auth.backend import (
    AuthBackend,
    HttpAuthBackend,
    OfflineAuthBackend,
    SupabaseAuthBackend,
    UnconfiguredAuthBackend,
)
from ai_caster.auth.client import AuthClient
from ai_caster.auth.events import AuthStateChanged
from ai_caster.auth.factory import create_auth_backend
from ai_caster.auth.models import Account, AuthResult, AuthSession
from ai_caster.auth.roles import (
    DEFAULT_ROLE,
    Role,
    assignable_roles,
    at_least,
    can_assign,
    can_manage_roles,
    can_train,
    rank,
)
from ai_caster.auth.store import SessionStore

__all__ = [
    "AuthBackend",
    "OfflineAuthBackend",
    "HttpAuthBackend",
    "SupabaseAuthBackend",
    "UnconfiguredAuthBackend",
    "create_auth_backend",
    "AuthClient",
    "AuthStateChanged",
    "Account",
    "AuthSession",
    "AuthResult",
    "SessionStore",
    "Role",
    "DEFAULT_ROLE",
    "rank",
    "at_least",
    "can_train",
    "can_manage_roles",
    "assignable_roles",
    "can_assign",
]
