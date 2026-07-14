"""Module 3 — Authentication Client.

Sign-in/out and session management behind an :class:`AuthBackend` interface. The
default backend authenticates locally (offline, deterministic, no server), so the
account surface is fully usable and testable without a backend; an HTTP backend
talks to a real account service in production. The client persists the session
for "remember me" and announces sign-in state on the event bus.
"""

from ai_caster.auth.backend import AuthBackend, HttpAuthBackend, OfflineAuthBackend
from ai_caster.auth.client import AuthClient
from ai_caster.auth.events import AuthStateChanged
from ai_caster.auth.models import Account, AuthResult, AuthSession
from ai_caster.auth.store import SessionStore

__all__ = [
    "AuthBackend",
    "OfflineAuthBackend",
    "HttpAuthBackend",
    "AuthClient",
    "AuthStateChanged",
    "Account",
    "AuthSession",
    "AuthResult",
    "SessionStore",
]
