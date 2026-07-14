"""Deployment defaults baked into a distributed build.

A shipped product can come **pre-configured** (e.g. pointed at a specific Supabase
project) without the operator editing anything. Those defaults are read from two
sources, merged (env wins):

1. A bundled ``ai_caster/deploy_defaults.json`` — written at build time from CI
   secrets, so keys never live in the (public) source tree. It may contain any
   subset of the settings document.
2. ``AI_CASTER_SUPABASE_URL`` / ``AI_CASTER_SUPABASE_ANON_KEY`` environment
   variables — a convenient shortcut (mainly for development) that sets the
   account provider to Supabase.

Defaults are applied only when a fresh settings file is created (see
:class:`~ai_caster.config.manager.SettingsManager`), so a user's own configuration
is never overwritten. The **anon** key is public by design; the service-role key
and database password must never be placed here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ai_caster.core.logging import get_logger

_log = get_logger("config.deploy")

_BUNDLED = Path(__file__).resolve().parent.parent / "deploy_defaults.json"


def _deep_merge(base: dict, overrides: dict) -> dict:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _load_bundled() -> dict:
    if not _BUNDLED.is_file():
        return {}
    try:
        data = json.loads(_BUNDLED.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Ignoring unreadable deploy_defaults.json (%s).", exc)
        return {}


def _from_env() -> dict:
    url = os.environ.get("AI_CASTER_SUPABASE_URL", "").strip()
    key = os.environ.get("AI_CASTER_SUPABASE_ANON_KEY", "").strip()
    if url and key:
        return {
            "account": {
                "provider": "supabase",
                "supabase_url": url,
                "supabase_anon_key": key,
            }
        }
    return {}


def deploy_overrides() -> dict[str, Any]:
    """Merged deployment override dict (empty when nothing is configured)."""
    overrides = _load_bundled()
    env = _from_env()
    if env:
        _deep_merge(overrides, env)
    return overrides


def apply_deploy_defaults(base):
    """Return ``base`` (an :class:`AppSettings`) with deployment overrides merged in.

    On any validation problem the original ``base`` is returned unchanged, so a bad
    deploy file can never stop the app from starting.
    """
    from ai_caster.config.models import AppSettings

    overrides = deploy_overrides()
    if not overrides:
        return base
    data = base.model_dump(mode="json")
    _deep_merge(data, overrides)
    try:
        merged = AppSettings.model_validate(data)
        _log.info("Applied deployment defaults for sections: %s", ", ".join(sorted(overrides)))
        return merged
    except Exception as exc:  # noqa: BLE001 - never let bad defaults block startup
        _log.warning("Deployment defaults were invalid (%s); ignoring them.", exc)
        return base
