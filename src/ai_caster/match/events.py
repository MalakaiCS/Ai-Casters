"""Engine-level match events published on the bus.

Distinct from *detected* events (:mod:`ai_caster.detection.events`): this is the
"the whole model was refreshed" signal the UI and future commentary modules use
to read the latest :class:`~ai_caster.match.model.LiveMatch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_caster.core.events import Event


@dataclass(frozen=True)
class MatchModelUpdated(Event):
    """The live match model was rebuilt from a new GSI payload.

    ``match`` is an immutable :class:`~ai_caster.match.model.LiveMatch`; typed as
    ``Any`` here to keep :mod:`core`-adjacent code free of import cycles.
    """

    match: Any = None
