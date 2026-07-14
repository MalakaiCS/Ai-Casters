"""Generator for the CS2 Game State Integration config file.

CS2 enables GSI when a ``gamestate_integration_*.cfg`` file is present in the
game's ``csgo/cfg`` directory. This module builds that file's contents to match
the app's configured host/port/token so users don't have to hand-edit it.

The file uses Valve's KeyValues syntax. The ``data`` block requests every
component the caster can use; the ``auth`` block carries the shared token the
receiver validates.
"""

from __future__ import annotations

from pathlib import Path

_CONFIG_NAME = "gamestate_integration_ai_caster.cfg"


def build_gsi_config(
    *,
    host: str = "127.0.0.1",
    port: int = 3111,
    auth_token: str = "",
    heartbeat: float = 0.1,
) -> str:
    """Return the text of a CS2 GSI config file.

    Parameters
    ----------
    host / port:
        Where CS2 should POST. Must match the running :class:`GSIServer`.
    auth_token:
        Shared secret echoed back in every payload's ``auth`` block.
    heartbeat:
        Seconds; forces an update at least this often even without changes.
    """
    uri = f"http://{host}:{port}/"
    return f'''"AI Esports Caster Integration"
{{
    "uri"          "{uri}"
    "timeout"      "5.0"
    "buffer"       "0.1"
    "throttle"     "0.1"
    "heartbeat"    "{heartbeat}"
    "auth"
    {{
        "token"    "{auth_token}"
    }}
    "data"
    {{
        "provider"                 "1"
        "map"                      "1"
        "round"                    "1"
        "player_id"                "1"
        "player_state"             "1"
        "player_weapons"           "1"
        "player_match_stats"       "1"
        "allplayers_id"            "1"
        "allplayers_state"         "1"
        "allplayers_match_stats"   "1"
        "allplayers_weapons"       "1"
        "allplayers_position"      "1"
        "phase_countdowns"         "1"
        "bomb"                     "1"
    }}
}}
'''


def write_gsi_config(
    directory: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 3111,
    auth_token: str = "",
    filename: str = _CONFIG_NAME,
) -> Path:
    """Write the GSI config into ``directory`` and return the file path.

    ``directory`` is typically the game's ``csgo/cfg`` folder. It is created if
    missing.
    """
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(build_gsi_config(host=host, port=port, auth_token=auth_token), encoding="utf-8")
    return path
