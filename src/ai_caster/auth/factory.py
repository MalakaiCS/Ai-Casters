"""Build the authentication backend from settings.

Selecting a provider whose configuration is incomplete (e.g. Supabase without a
URL/key) degrades to the offline backend with a warning rather than crashing, so
the account surface always works.
"""

from __future__ import annotations

from ai_caster.auth.backend import (
    AuthBackend,
    HttpAuthBackend,
    OfflineAuthBackend,
    SupabaseAuthBackend,
)
from ai_caster.config.models import AccountProvider, AccountSettings
from ai_caster.core.logging import get_logger

_log = get_logger("auth.factory")


def create_auth_backend(settings: AccountSettings) -> AuthBackend:
    """Construct the configured auth backend, or Offline if it isn't usable."""
    provider = settings.provider

    if provider is AccountProvider.SUPABASE:
        if settings.supabase_url and settings.supabase_anon_key:
            return SupabaseAuthBackend(settings.supabase_url, settings.supabase_anon_key)
        _log.warning("Supabase selected but URL/anon key are missing; using offline auth.")
        return OfflineAuthBackend()

    if provider is AccountProvider.HTTP:
        if settings.server_url:
            return HttpAuthBackend(settings.server_url)
        _log.warning("HTTP account provider selected but server_url is empty; using offline auth.")
        return OfflineAuthBackend()

    return OfflineAuthBackend()
