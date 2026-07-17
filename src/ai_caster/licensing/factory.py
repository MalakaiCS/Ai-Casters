"""Build the licensing backend from settings.

Supabase reuses the project URL + anon key configured under Account settings, so
one Supabase project backs both auth and licensing. A misconfigured provider
degrades to the offline (free) backend rather than failing.
"""

from __future__ import annotations

from ai_caster.config.models import AccountProvider, AccountSettings, LicensingSettings
from ai_caster.core.logging import get_logger
from ai_caster.licensing.backend import (
    HttpLicensingBackend,
    LicensingBackend,
    OfflineLicensingBackend,
    SupabaseLicensingBackend,
)

_log = get_logger("licensing.factory")


def create_licensing_backend(
    licensing: LicensingSettings, account: AccountSettings
) -> LicensingBackend:
    """Construct the configured licensing backend, or Offline if it isn't usable."""
    if licensing.provider is AccountProvider.SUPABASE:
        if account.supabase_url and account.supabase_anon_key:
            return SupabaseLicensingBackend(
                account.supabase_url,
                account.supabase_anon_key,
                device_name=licensing.device_name,
            )
        _log.warning("Supabase licensing selected but URL/anon key are missing; using offline.")
        return OfflineLicensingBackend()

    if licensing.provider is AccountProvider.HTTP and licensing.server_url:
        return HttpLicensingBackend(licensing.server_url)

    return OfflineLicensingBackend()
