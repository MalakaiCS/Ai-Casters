"""Vision events published on the bus.

Like capture, vision does not publish per-frame at full rate; it publishes a
consolidated :class:`VisionStateUpdated` at the (throttled) analysis rate. These
subclass the core :class:`~ai_caster.core.events.Event` so they route to the UI,
the match engine (for fusion) and later the Commentary Director.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class VisionStateUpdated(Event):
    """A frame was analysed. ``state`` is an immutable
    :class:`~ai_caster.vision.state.VisionState` (typed ``Any`` to avoid import
    cycles in :mod:`core`-adjacent code)."""

    state: Any = None
