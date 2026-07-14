"""Build the settings-sync backend from settings.

Supabase reuses the project URL + anon key configured under Account settings. A
misconfigured provider degrades to the local no-op backend.
"""

from __future__ import annotations

from ai_caster.config.models import AccountProvider, AccountSettings, SyncSettings
from ai_caster.core.logging import get_logger
from ai_caster.sync.backend import (
    HttpSyncBackend,
    NullSyncBackend,
    SupabaseSyncBackend,
    SyncBackend,
)

_log = get_logger("sync.factory")


def create_sync_backend(sync: SyncSettings, account: AccountSettings) -> SyncBackend:
    """Construct the configured sync backend, or the local no-op if it isn't usable."""
    if sync.provider is AccountProvider.SUPABASE:
        if account.supabase_url and account.supabase_anon_key:
            return SupabaseSyncBackend(account.supabase_url, account.supabase_anon_key)
        _log.warning("Supabase sync selected but URL/anon key are missing; using local no-op.")
        return NullSyncBackend()

    if sync.provider is AccountProvider.HTTP and sync.server_url:
        return HttpSyncBackend(sync.server_url)

    return NullSyncBackend()
