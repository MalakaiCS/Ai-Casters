"""Stable per-install device identity.

Licensing and device management need a durable id for *this* installation that
survives restarts but is not tied to volatile hardware details. We generate a
random UUID once and persist it under the config directory; every later call
returns the same value. Kept in :mod:`core` because both the auth and licensing
clients depend on it.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ai_caster.core.logging import get_logger

_log = get_logger("core.identity")

_DEVICE_FILE = "device.json"


def get_or_create_device_id(config_dir: Path) -> str:
    """Return this install's device id, creating and persisting one if absent."""
    path = Path(config_dir) / _DEVICE_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            device_id = str(data.get("device_id", "")).strip()
            if device_id:
                return device_id
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning("Could not read device id (%s); regenerating.", exc)

    device_id = uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"device_id": device_id}), encoding="utf-8")
    except OSError:
        _log.exception("Could not persist device id; using an ephemeral one.")
    return device_id
