"""Broadcast control (M9).

One controller that turns the whole cast on/off, master-mutes the voices, and
forces replay mode — the single code path shared by the UI and the global
hotkeys. Casting is gated on the ``LIVE_CASTING`` entitlement.
"""

from ai_caster.broadcast.controller import BroadcastController
from ai_caster.broadcast.events import BroadcastStateChanged

__all__ = ["BroadcastController", "BroadcastStateChanged"]
