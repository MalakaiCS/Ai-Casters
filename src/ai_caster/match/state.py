"""The match state store.

This is the foundation of the Match State Engine (Module 8, fully built in M2).
In Milestone 1 it holds the latest GSI-derived snapshot in a thread-safe way and
records the **source** and **confidence** of the data, so that when Vision (M4)
and inference are added, the documented priority

    Server events > GSI > Vision > Inference

can be enforced without reworking consumers. The store never lets uncertain data
overwrite higher-priority confirmed data — a rule encoded here from day one.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imported for annotations only. A runtime import here would create a cycle
    # (gsi.__init__ -> gsi.receiver -> match.state), so we keep it type-only;
    # `from __future__ import annotations` makes every annotation a string.
    from ai_caster.gsi.models import GameState


class DataSource(IntEnum):
    """Priority ordering of truth sources. Higher wins."""

    INFERENCE = 1
    VISION = 2
    GSI = 3
    SERVER = 4


@dataclass(frozen=True)
class MatchSnapshot:
    """An immutable point-in-time view of the match.

    Milestone 1 exposes the headline fields the UI shows and keeps the full
    parsed :class:`GameState` for anything else. Later milestones enrich this
    with fused, multi-source fields.
    """

    updated_at: datetime
    source: DataSource
    game_state: GameState | None = None

    # Denormalised headline fields (cheap for the UI to read).
    map_name: str | None = None
    round_number: int | None = None
    ct_score: int | None = None
    t_score: int | None = None
    round_phase: str | None = None
    match_phase: str | None = None
    bomb: str | None = None
    observed_player: str | None = None
    players_alive: int | None = None

    @classmethod
    def from_game_state(
        cls, state: GameState, *, source: DataSource = DataSource.GSI
    ) -> MatchSnapshot:
        """Build a snapshot from a parsed GSI payload."""
        alive = None
        if state.allplayers:
            alive = sum(
                1
                for p in state.allplayers.values()
                if p.state is not None and (p.state.health or 0) > 0
            )
        return cls(
            updated_at=datetime.now(UTC),
            source=source,
            game_state=state,
            map_name=state.map_name,
            round_number=state.round_number,
            ct_score=state.ct_score,
            t_score=state.t_score,
            round_phase=state.round.phase if state.round else None,
            match_phase=state.map.phase if state.map else None,
            bomb=state.round.bomb if state.round else None,
            observed_player=state.observed_player_name,
            players_alive=alive,
        )


@dataclass
class MatchStateStore:
    """Thread-safe holder of the latest :class:`MatchSnapshot`.

    Consumers (UI, future commentary modules) read :meth:`snapshot`. Producers
    call :meth:`apply`. Implements
    :class:`~ai_caster.core.interfaces.MatchStateProvider`.
    """

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _snapshot: MatchSnapshot | None = field(default=None, repr=False)

    def apply(self, snapshot: MatchSnapshot) -> bool:
        """Store ``snapshot`` if it is at least as authoritative as the current
        one.

        Returns ``True`` if it was applied. This is where the priority-of-truth
        rule lives: a lower-priority source (e.g. Vision) never overwrites a
        newer, higher-priority one (e.g. GSI/Server). Equal-or-higher priority
        always wins, which for the GSI-only M1 case means "latest wins".
        """
        with self._lock:
            current = self._snapshot
            if current is not None and snapshot.source < current.source:
                # A weaker source cannot clobber stronger, still-fresh data.
                if snapshot.updated_at <= current.updated_at:
                    return False
            self._snapshot = snapshot
            return True

    def snapshot(self) -> MatchSnapshot | None:
        """Return the latest snapshot (or ``None`` if nothing received yet)."""
        with self._lock:
            return self._snapshot

    def clear(self) -> None:
        with self._lock:
            self._snapshot = None
