"""Decide *when* casting begins in a match.

Some productions want the desk quiet until the match proper starts — no warm-up
chatter, or no knife-round talk. This gate watches the match-event stream and
holds all commentary until the configured start point is reached:

* ``ASAP`` — open immediately (the default; warm-up included).
* ``KNIFE_ROUND`` — open when the knife round starts (or, if there is no knife
  round, at the first live round).
* ``ROUND_1`` — open at the first scored round, skipping warm-up and the knife
  round.

The Director and the downtime commentator consult :attr:`is_open` before emitting
anything, so a single gate governs the whole desk. Once opened it stays open for
the match and re-arms when a new match starts.
"""

from __future__ import annotations

import threading

from ai_caster.config.models import CastStart
from ai_caster.core.logging import get_logger
from ai_caster.detection.events import KnifeRound, MatchEvent, MatchStarted, RoundStarted

_log = get_logger("director.cast_gate")


class CastGate:
    """Gates commentary until the configured start point of the match."""

    def __init__(self, event_bus, *, mode: CastStart = CastStart.ASAP) -> None:  # noqa: ANN001
        self._lock = threading.RLock()
        self._mode = mode
        self._open = mode == CastStart.ASAP
        self._knife_seen = False
        self._round_starts = 0
        self._unsubscribe = event_bus.subscribe(MatchEvent, self._on_event)

    # ------------------------------------------------------------------ #
    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._open

    @property
    def mode(self) -> CastStart:
        with self._lock:
            return self._mode

    def set_mode(self, mode: CastStart) -> None:
        """Change the start point. Opening ASAP takes effect at once; switching to
        a later start mid-match never *silences* a desk that already began."""
        with self._lock:
            self._mode = mode
            if mode == CastStart.ASAP:
                self._open = True

    def reset(self) -> None:
        with self._lock:
            self._knife_seen = False
            self._round_starts = 0
            self._open = self._mode == CastStart.ASAP

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    # ------------------------------------------------------------------ #
    def _on_event(self, event: MatchEvent) -> None:
        with self._lock:
            # A new match re-arms the gate so the next game honours the setting.
            if isinstance(event, MatchStarted):
                self._knife_seen = False
                self._round_starts = 0
                self._open = self._mode == CastStart.ASAP
                return
            if self._open:
                return
            self._evaluate(event)

    def _evaluate(self, event: MatchEvent) -> None:
        """Open the gate if this event satisfies the start mode (called under lock).

        Event ordering within a tick matters and is guaranteed by the detector:
        ``KnifeRound`` is emitted before that round's ``RoundStarted``.
        """
        if isinstance(event, KnifeRound):
            self._knife_seen = True
            if self._mode == CastStart.KNIFE_ROUND:
                self._opened("knife round")
            return
        if isinstance(event, RoundStarted):
            self._round_starts += 1
            if self._mode == CastStart.KNIFE_ROUND:
                # First live round — covers matches played without a knife round.
                self._opened("first round")
            elif self._mode == CastStart.ROUND_1:
                if not self._knife_seen:
                    self._opened("round 1")  # no knife round -> first start is round 1
                elif self._round_starts >= 2:
                    self._opened("round 1")  # knife was start #1; this is round 1

    def _opened(self, why: str) -> None:
        self._open = True
        _log.info("Casting gate opened (%s)", why)
