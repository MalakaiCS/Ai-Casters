"""Build the authentication backend from settings.

Accounts are **Supabase-only** in a shipped build. When Supabase is configured
(URL + anon key), the real :class:`SupabaseAuthBackend` is used. When it is not,
a *packaged* build gets the :class:`UnconfiguredAuthBackend`, which refuses every
sign-in with a clear message rather than accepting anything — so a build made
without the deployment secrets can never masquerade as a working account system.

The deterministic :class:`OfflineAuthBackend` remains available for local
development and the test suite (an un-frozen process with the ``offline``
provider), but it is never the fallback for a distributed application.
"""

from __future__ import annotations

import sys

from ai_caster.auth.backend import (
    AuthBackend,
    HttpAuthBackend,
    OfflineAuthBackend,
    SupabaseAuthBackend,
    UnconfiguredAuthBackend,
)
from ai_caster.config.models import AccountProvider, AccountSettings
from ai_caster.core.logging import get_logger

_log = get_logger("auth.factory")


def _is_frozen() -> bool:
    """True when running inside a packaged (PyInstaller) build."""
    return bool(getattr(sys, "frozen", False))


def _fallback() -> AuthBackend:
    """The safe fallback when no real service is configured.

    A packaged build must never accept arbitrary credentials, so it gets the
    unconfigured backend (sign-in disabled). Development/test processes get the
    offline backend so the account surface stays usable without a server.
    """
    if _is_frozen():
        _log.warning("No account service configured in a packaged build; sign-in disabled.")
        return UnconfiguredAuthBackend()
    return OfflineAuthBackend()


def create_auth_backend(settings: AccountSettings) -> AuthBackend:
    """Construct the configured auth backend for the current build."""
    provider = settings.provider

    if provider is AccountProvider.SUPABASE:
        if settings.supabase_url and settings.supabase_anon_key:
            return SupabaseAuthBackend(settings.supabase_url, settings.supabase_anon_key)
        # Supabase was selected but isn't usable: never silently accept anything.
        _log.warning("Supabase selected but URL/anon key are missing; sign-in disabled.")
        return UnconfiguredAuthBackend()

    if provider is AccountProvider.HTTP:
        if settings.server_url:
            return HttpAuthBackend(settings.server_url)
        _log.warning("HTTP account provider selected but server_url is empty.")
        return _fallback()

    return _fallback()
