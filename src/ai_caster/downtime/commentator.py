"""Downtime commentary — keep the desk talking when nothing is happening.

Two related jobs, both driven off one light timer:

* **Lulls** — a called timeout, a paused match, half-time or warm-up. Once a lull
  has lasted past a short delay it periodically issues a low-key directive: the
  analyst covering *what to expect* from the team that called a timeout, the
  play-by-play caster keeping the desk warm with a stat or two.
* **Slow live rounds** — a genuinely live round with no kills or plants for a
  while (a methodical, patient round). Rather than go silent it adds light filler:
  the analyst on map control / the economy read, the play-by-play caster on the
  score and momentum. It resets the moment real action happens again.

Both stay LOW priority and never interrupt, and both yield entirely to replays.

The *decision* (:meth:`tick`) is separated from the timer thread so it's fully
unit-tested with a fake clock; the thread just publishes whatever ``tick``
returns onto the same bus the live director uses, so the existing generators and
voices speak it with no special casing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ai_caster.commentary.mapcontrol import area_for
from ai_caster.core.logging import get_logger
from ai_caster.director.directives import (
    CommentaryDirective,
    CommentaryDirectiveIssued,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)
from ai_caster.downtime.detect import LullState, detect_lull, is_live_round
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
        slow_round_enabled: bool = True,
        slow_round_after_seconds: float = 16.0,
        slow_round_interval_seconds: float = 18.0,
        round_intro_seconds: float = 6.0,
        tick_seconds: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        cast_gate=None,  # noqa: ANN001 - CastGate | None
    ) -> None:
        self._bus = event_bus
        self._enabled = enabled
        self._cast_gate = cast_gate
        self._min_delay = min_delay_seconds
        self._interval = interval_seconds
        self._slow_enabled = slow_round_enabled
        self._slow_after = slow_round_after_seconds
        self._slow_interval = slow_round_interval_seconds
        self._intro_seconds = round_intro_seconds
        self._tick = tick_seconds
        self._clock = clock

        self._lock = threading.RLock()
        self._match: LiveMatch | None = None
        self._replay_active = False
        self._lull_since: float | None = None
        self._live_since: float | None = None  # when the current live round began
        self._last_activity: float = float("-inf")  # last real match event we saw
        self._last_spoke: float = float("-inf")  # so the first fill isn't rate-limited
        self._rotation = 0
        self._quiet_rotation = 0
        self._area_rotation = 0
        self._intro_pending = False  # a fresh live round wants an opening map-control line

        self._running = False
        self._thread: threading.Thread | None = None
        self._unsubscribes = [
            event_bus.subscribe(MatchModelUpdated, self._on_model),
            event_bus.subscribe(ReplayStateChanged, self._on_replay),
            event_bus.subscribe(CommentaryDirectiveIssued, self._on_directive),
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
            # Track when a live round begins so quiet-round filler measures the
            # silence from the moment play actually started. A fresh live round arms
            # the opening map-control line (Stage 1).
            if is_live_round(match):
                if self._live_since is None:
                    self._live_since = self._clock()
                    self._intro_pending = True
            else:
                self._live_since = None
                self._intro_pending = False

    def _on_replay(self, event: ReplayStateChanged) -> None:
        self.on_replay(getattr(event.state, "active", False))

    def on_replay(self, active: bool) -> None:
        with self._lock:
            self._replay_active = bool(active)

    def _on_directive(self, event: CommentaryDirectiveIssued) -> None:
        """Note real match activity so quiet-round filler only fires into silence."""
        directive = event.directive
        if directive is None:
            return
        reason = directive.reason or ""
        # Ignore our own filler (downtime:/quiet:) — only live action counts.
        if reason.startswith(("downtime:", "quiet:")):
            return
        with self._lock:
            self._last_activity = self._clock()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    def set_slow_round_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._slow_enabled = enabled

    # -- decision (pure-ish; fully testable) ---------------------------- #
    def tick(self, now: float) -> CommentaryDirective | None:
        """Return a directive to speak right now, or None."""
        with self._lock:
            if not self._enabled or self._replay_active:
                return None
            if self._cast_gate is not None and not self._cast_gate.is_open:
                return None  # desk hasn't been cleared to start talking yet
            match = self._match
            lull = detect_lull(match)
            if lull.active:
                return self._tick_lull(now, lull, match)
            # No lull — keep the current live round from going silent.
            self._lull_since = None
            return self._tick_quiet(now, match)

    def _tick_lull(
        self, now: float, lull: LullState, match: LiveMatch | None
    ) -> CommentaryDirective | None:
        if self._lull_since is None:
            self._lull_since = now
        if now - self._lull_since < self._min_delay:
            return None
        if now - self._last_spoke < self._interval:
            return None
        directive = self._build_directive(lull, match, self._rotation)
        self._last_spoke = now
        self._rotation += 1
        return directive

    def _tick_quiet(self, now: float, match: LiveMatch | None) -> CommentaryDirective | None:
        if not self._slow_enabled or not is_live_round(match) or self._live_since is None:
            return None
        stage = getattr(match, "round_stage", 1) or 1
        # Opening map-control line: fill the gap early in Stage 1 (the start of the
        # round) rather than waiting for the full quiet window.
        if self._intro_pending and stage == 1:
            if now - self._live_since >= self._intro_seconds and now - self._last_activity >= (
                self._intro_seconds
            ):
                self._intro_pending = False
                self._last_spoke = now
                return self._build_map_control_directive(match)
            return None
        # Otherwise the regular stage-aware quiet fill on the slow-round cadence.
        quiet_since = max(self._live_since, self._last_activity)
        if now - quiet_since < self._slow_after:
            return None
        if now - self._last_spoke < self._slow_interval:
            return None
        directive = self._build_quiet_directive(match, self._quiet_rotation, stage)
        self._last_spoke = now
        self._quiet_rotation += 1
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

    def _build_map_control_directive(self, match: LiveMatch | None) -> CommentaryDirective:
        """The opening Stage-1 line: the fight for map control, framed as expectation."""
        map_name = getattr(match, "map_name", None) or "this map"
        area = area_for(map_name, self._area_rotation)
        self._area_rotation += 1
        context = {
            "map": map_name,
            "area": area,
            "ct_team": self._team_name(match, Side.CT),
            "t_team": self._team_name(match, Side.T),
            "ct_buy": self._buy(match, Side.CT),
            "t_buy": self._buy(match, Side.T),
        }
        return CommentaryDirective(
            speaker=Speaker.ANALYST,
            kind=DirectiveKind.ANALYZE,
            priority=DirectivePriority.LOW,
            excitement=0.25,
            topic="map_control",
            interrupt=False,
            reason="quiet:map_control",
            context=context,
        )

    def _build_quiet_directive(
        self, match: LiveMatch | None, rotation: int, stage: int
    ) -> CommentaryDirective:
        speaker, topic, context = self._plan_quiet(match, rotation, stage)
        kind = DirectiveKind.CALL if speaker is Speaker.PLAY_BY_PLAY else DirectiveKind.ANALYZE
        return CommentaryDirective(
            speaker=speaker,
            kind=kind,
            priority=DirectivePriority.LOW,
            excitement=0.2,
            topic=topic,
            interrupt=False,
            reason=f"quiet:stage{stage}",
            context=context,
        )

    def _plan_quiet(
        self, match: LiveMatch | None, rotation: int, stage: int
    ) -> tuple[Speaker, str, dict]:
        """Stage-aware light filler for a quiet live round, using real facts only."""
        score = self._score(match)
        map_name = getattr(match, "map_name", None) or "this map"
        rounds = getattr(match, "round_number", 0) or 0
        ct_team = self._team_name(match, Side.CT)
        t_team = self._team_name(match, Side.T)

        # Stage 3 (late round): the clock is the story.
        if stage >= 3:
            seconds = getattr(match, "round_time_left", None)
            return (
                Speaker.PLAY_BY_PLAY,
                "late_round",
                {
                    "score": score,
                    "seconds": int(seconds) if seconds is not None else None,
                    "t_team": t_team,
                    "ct_team": ct_team,
                    "map": map_name,
                },
            )

        # Stage 1/2 (mostly mid-round): rotate positioning / economy / stat.
        slot = rotation % 3
        if slot == 0:
            return (
                Speaker.ANALYST,
                "slow_round_positioning",
                {
                    "map": map_name,
                    "area": area_for(map_name, rotation),
                    "ct_team": ct_team,
                    "t_team": t_team,
                    "ct_alive": self._alive(match, Side.CT),
                    "t_alive": self._alive(match, Side.T),
                },
            )
        if slot == 1:
            return (
                Speaker.ANALYST,
                "slow_round_economy",
                {
                    "ct_buy": self._buy(match, Side.CT),
                    "t_buy": self._buy(match, Side.T),
                    "ct_team": ct_team,
                    "t_team": t_team,
                    "map": map_name,
                },
            )
        return (
            Speaker.PLAY_BY_PLAY,
            "slow_round_stat",
            {
                "score": score,
                "round": rounds,
                "map": map_name,
                "momentum_leader": self._momentum_leader(match),
            },
        )

    @staticmethod
    def _alive(match: LiveMatch | None, side: Side) -> int | None:
        if match is None:
            return None
        return match.team(side).players_alive

    @staticmethod
    def _buy(match: LiveMatch | None, side: Side) -> str:
        if match is None:
            return "unknown"
        return match.team(side).buy_type.value

    @staticmethod
    def _momentum_leader(match: LiveMatch | None) -> str | None:
        if match is None:
            return None
        leader = match.momentum.leader
        return leader.value if leader is not None else None

    @staticmethod
    def _score(match: LiveMatch | None) -> str:
        if match is None:
            return "0-0"
        return f"{match.ct.score}-{match.t.score}"

    @staticmethod
    def _team_name(match: LiveMatch | None, side: Side) -> str:
        if match is None:
            return "that team"
        namer = getattr(match, "team_name", None)
        if namer is not None:
            return namer(side)
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
