"""Global hotkeys (Module 1 completion, M9).

Maps configured key combinations to broadcast actions (toggle casting, mute all,
force replay mode). The default backend installs no OS hook — the same actions
stay reachable from the UI — while an optional pynput backend registers true
global hotkeys behind the ``[hotkeys]`` extra.
"""

from ai_caster.hotkeys.actions import HotkeyAction
from ai_caster.hotkeys.backend import HotkeyBackend, NullHotkeyBackend, PynputHotkeyBackend
from ai_caster.hotkeys.manager import HotkeyManager

__all__ = [
    "HotkeyAction",
    "HotkeyBackend",
    "NullHotkeyBackend",
    "PynputHotkeyBackend",
    "HotkeyManager",
]
