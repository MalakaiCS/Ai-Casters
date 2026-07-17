"""The set of global-hotkey actions."""

from __future__ import annotations

from enum import StrEnum


class HotkeyAction(StrEnum):
    """Actions a global hotkey can trigger. Bound to controller methods."""

    TOGGLE_CASTING = "toggle_casting"
    MUTE_ALL = "mute_all"
    FORCE_REPLAY_MODE = "force_replay_mode"
