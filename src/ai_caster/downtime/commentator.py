"""Downtime commentary — fill timeouts, pauses and breaks with desk chatter.

During a broadcast lull there are no match events to react to, so this service
runs a light timer: once a lull has lasted past a short delay, it periodically
issues a low-key directive — the analyst covering *what to expect* from the team
that called a timeout, the play-by-play caster keeping the desk warm with a stat
or two — and stops the moment live action resumes. It never interrupts (LOW
priority, ``interrupt=False``) and yields entirely to replays.

The *decision* (:meth:`tick`) is separated from the timer thread so it's fully
unit-tested with a fake clock; the thread just publishes whatever ``tick``
returns onto the same bus the live director uses, so the existing generators and
voices speak it with no special casing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ai_caster.core.logging import get_logger
from ai_caster.director.directives import (
    CommentaryDirective,
    CommentaryDirectiveIssued,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)
from ai_caster.downtime.detect import LullState, detect_lull
from ai_caster.match.events import MatchModelUpdated
from ai_caster.match.model import LiveMatch, Side
from ai_caster.replay.events import ReplayStateChanged

_log = get_logger("downtime")


class DowntimeCommentator:
    """Issues casual commentary during timeouts, pauses and breaks."""

    def __init__(
        self,
        event_bus,  # noqa: ANN001 - EventBus
        *,
        enabled: bool = True,
        min_delay_seconds: float = 12.0,
        interval_seconds: float = 25.0,
        tick_seconds: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = event_bus
        self._enabled = enabled
        self._min_delay = min_delay_seconds
        self._interval = interval_seconds
        self._tick = tick_seconds
        self._clock = clock

        self._lock = threading.RLock()
        self._match: LiveMatch | None = None
        self._replay_active = False
        self._lull_since: float | None = None
        self._last_spoke: float = float("-inf")  # so the first fill isn't rate-limited
        self._rotation = 0

        self._running = False
        self._thread: threading.Thread | None = None
        self._unsubscribes = [
            event_bus.subscribe(MatchModelUpdated, self._on_model),
            event_bus.subscribe(ReplayStateChanged, self._on_replay),
        ]

    # -- inputs --------------------------------------------------------- #
    def _on_model(self, event: MatchModelUpdated) -> None:
        self.on_model(event.match)

    def on_model(self, match: LiveMatch | None) -> None:
        with self._lock:
            self._match = match
            lull = detect_lull(match)
            if lull.active:
                if self._lull_since is None:
                    self._lull_since = self._clock()
            else:
                self._lull_since = None

    def _on_replay(self, event: ReplayStateChanged) -> None:
        self.on_replay(getattr(event.state, "active", False))

    def on_replay(self, active: bool) -> None:
        with self._lock:
            self._replay_active = bool(active)

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    # -- decision (pure-ish; fully testable) ---------------------------- #
    def tick(self, now: float) -> CommentaryDirective | None:
        """Return a directive to speak right now, or None."""
        with self._lock:
            if not self._enabled or self._replay_active or self._lull_since is None:
                return None
            match = self._match
            lull = detect_lull(match)
            if not lull.active:
                self._lull_since = None
                return None
            if now - self._lull_since < self._min_delay:
                return None
            if now - self._last_spoke < self._interval:
                return None
            directive = self._build_directive(lull, match, self._rotation)
            self._last_spoke = now
            self._rotation += 1
            return directive

    def _build_directive(
        self, lull: LullState, match: LiveMatch | None, rotation: int
    ) -> CommentaryDirective:
        speaker, topic, context = self._plan(lull, match, rotation)
        kind = DirectiveKind.CALL if speaker is Speaker.PLAY_BY_PLAY else DirectiveKind.ANALYZE
        return CommentaryDirective(
            speaker=speaker,
            kind=kind,
            priority=DirectivePriority.LOW,
            excitement=0.25,
            topic=topic,
            interrupt=False,
            reason=f"downtime:{lull.kind}",
            context=context,
        )

    def _plan(
        self, lull: LullState, match: LiveMatch | None, rotation: int
    ) -> tuple[Speaker, str, dict]:
        score = self._score(match)
        map_name = getattr(match, "map_name", None) or "this map"
        rounds = getattr(match, "round_number", 0) or 0
        analyst_turn = rotation % 2 == 0

        if lull.kind == "timeout" and lull.timeout_side is not None and analyst_turn:
            team = self._team_name(match, lull.timeout_side)
            return (
                Speaker.ANALYST,
                "timeout_expectation",
                {"team": team, "side": lull.timeout_side.value, "score": score, "map": map_name},
            )
        if lull.kind in ("halftime", "paused") and analyst_turn:
            return (Speaker.ANALYST, "halftime_recap", {"score": score, "map": map_name})
        if lull.kind == "warmup" and analyst_turn:
            return (Speaker.ANALYST, "warmup_preview", {"map": map_name})

        # Play-by-play keeps the desk warm with a stat or a breather.
        if lull.kind == "warmup":
            return (Speaker.PLAY_BY_PLAY, "downtime_chatter", {"map": map_name})
        return (
            Speaker.PLAY_BY_PLAY,
            "downtime_stat",
            {"score": score, "round": rounds, "map": map_name},
        )

    @staticmethod
    def _score(match: LiveMatch | None) -> str:
        if match is None:
            return "0-0"
        return f"{match.ct.score}-{match.t.score}"

    @staticmethod
    def _team_name(match: LiveMatch | None, side: Side) -> str:
        if match is None:
            return "that team"
        return match.team(side).name or side.value

    # -- lifecycle ------------------------------------------------------ #
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="downtime", daemon=True)
        self._thread.start()
        _log.info("Downtime commentator started")

    def _run(self) -> None:
        while self._running:
            time.sleep(self._tick)
            if not self._running:
                break
            try:
                directive = self.tick(self._clock())
            except Exception:  # noqa: BLE001 - never let the filler crash the app
                _log.exception("Downtime tick failed")
                continue
            if directive is not None:
                self._bus.publish(CommentaryDirectiveIssued(directive=directive))

    def dispose(self) -> None:
        self._running = False
        for unsub in self._unsubscribes:
            try:
                unsub()
            except Exception:  # noqa: BLE001 - best effort
                pass
        self._unsubscribes = []
