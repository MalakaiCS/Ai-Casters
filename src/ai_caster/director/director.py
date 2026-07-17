"""The Commentary Director.

Consumes match events, the live model, vision and replay state, and emits
:class:`CommentaryDirective` decisions that govern broadcast flow: speaker
selection, interruption/cancellation, rate-limited silence, replay transitions
and handoffs. It publishes directives on the bus; it never generates prose.

Enforcement of the core rule — *never describe replay footage as live* — lives
here: while an authoritative replay is active, play-by-play "call live action"
directives are suppressed with an explicit silence decision.

Thread-safety: bus handlers may run on network threads; all state is guarded by a
lock. A monotonic clock is injectable so interruption/rate-limit behaviour is
tested deterministically.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from ai_caster.core.events import EventBus
from ai_caster.core.logging import get_logger
from ai_caster.detection.events import ClutchWon, MatchEvent, RoundEnded
from ai_caster.director import policy
from ai_caster.director.directives import (
    CommentaryDirective,
    CommentaryDirectiveIssued,
    DirectiveKind,
    DirectivePriority,
    Speaker,
)
from ai_caster.match.events import MatchModelUpdated
from ai_caster.match.model import Side
from ai_caster.replay.events import ReplayStateChanged
from ai_caster.replay.models import ReplayType
from ai_caster.vision.events import VisionStateUpdated
from ai_caster.vision.observations import SceneType

_log = get_logger("director")

# Minimum excitement for the analyst to react to a play-by-play call live, so the
# banter beat only fires on genuinely big moments (not routine plays).
_BANTER_EXCITEMENT = 0.75


class CommentaryDirector:
    """Broadcast-flow controller."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        baseline_excitement: float = 0.7,
        allow_interruptions: bool = True,
        min_speech_gap: float = 0.8,
        excitement_contrast: float = 0.0,
        replay_integration_enabled: bool = True,
        treat_unknown_as_live: bool = False,
        history: int = 200,
        clock: Callable[[], float] = time.monotonic,
        cast_gate=None,  # noqa: ANN001 - CastGate | None
    ) -> None:
        self._bus = event_bus
        self._baseline = baseline_excitement
        self._allow_interruptions = allow_interruptions
        self._min_gap = min_speech_gap
        self._contrast = excitement_contrast
        self._replay_enabled = replay_integration_enabled
        self._treat_unknown_as_live = treat_unknown_as_live
        self._clock = clock
        self._cast_gate = cast_gate

        self._lock = threading.RLock()
        self._round_importance = 0.0
        self._series_importance = 0.0
        self._ct_name = "CT"
        self._t_name = "T"
        self._replay_active = False
        self._vision_replay = False
        self._current_priority = DirectivePriority.AMBIENT
        self._speaking_until = 0.0
        self._current_speaker = Speaker.NONE
        self._recent: deque[CommentaryDirective] = deque(maxlen=history)

        self._unsubscribes = [
            event_bus.subscribe(MatchEvent, self._on_match_event),
            event_bus.subscribe(MatchModelUpdated, self._on_model_updated),
            event_bus.subscribe(ReplayStateChanged, self._on_replay_changed),
            event_bus.subscribe(VisionStateUpdated, self._on_vision_updated),
        ]

    # ------------------------------------------------------------------ #
    # Live reconfiguration
    # ------------------------------------------------------------------ #
    def configure(
        self,
        *,
        baseline_excitement: float | None = None,
        allow_interruptions: bool | None = None,
        min_speech_gap: float | None = None,
        excitement_contrast: float | None = None,
    ) -> None:
        """Apply tone/pacing changes live (e.g. from the training/tuning UI)."""
        with self._lock:
            if baseline_excitement is not None:
                self._baseline = baseline_excitement
            if allow_interruptions is not None:
                self._allow_interruptions = allow_interruptions
            if min_speech_gap is not None:
                self._min_gap = min_speech_gap
            if excitement_contrast is not None:
                self._contrast = excitement_contrast

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #
    @property
    def is_live(self) -> bool:
        with self._lock:
            return policy.is_live_broadcast(
                replay_active=self._replay_active,
                replay_integration_enabled=self._replay_enabled,
                vision_suggests_replay=self._vision_replay,
                treat_unknown_as_live=self._treat_unknown_as_live,
            )

    @property
    def replay_active(self) -> bool:
        with self._lock:
            return self._replay_active

    @property
    def recent_directives(self) -> list[CommentaryDirective]:
        with self._lock:
            return list(self._recent)

    def dispose(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()

    # ------------------------------------------------------------------ #
    # Bus handlers
    # ------------------------------------------------------------------ #
    def _on_model_updated(self, event: MatchModelUpdated) -> None:
        if event.match is not None:
            with self._lock:
                self._round_importance = getattr(event.match, "round_importance", 0.0)
                self._series_importance = getattr(event.match, "series_importance", 0.0)
                # Capture team names (Faceit/ESEA feeds carry them) so commentary can
                # use them instead of "CT"/"T".
                namer = getattr(event.match, "team_name", None)
                if namer is not None:
                    self._ct_name = namer(Side.CT)
                    self._t_name = namer(Side.T)

    def _on_vision_updated(self, event: VisionStateUpdated) -> None:
        state = event.state
        if state is not None:
            # Only treat a *confident* replay-banner read as a replay hint; this
            # signal is consulted only when replay integration is unavailable,
            # and never outranks the authoritative external replay events.
            is_replay = getattr(state, "scene", None) == SceneType.REPLAY
            confidence = getattr(state, "scene_confidence", 0.0)
            with self._lock:
                self._vision_replay = is_replay and confidence >= 0.5

    def _on_match_event(self, event: MatchEvent) -> None:
        self.handle_match_event(event)

    def _on_replay_changed(self, event: ReplayStateChanged) -> None:
        self.handle_replay_change(event.state, event.transition)

    # ------------------------------------------------------------------ #
    # Decisions (public for testing)
    # ------------------------------------------------------------------ #
    def handle_match_event(self, event: MatchEvent) -> list[CommentaryDirective]:
        """Decide and publish directives for a match event."""
        if not self._casting_open():
            return []  # the desk hasn't been cleared to start talking yet
        with self._lock:
            directives = self._decide_match_event(event)
            for directive in directives:
                self._record(directive)
        for directive in directives:
            self._bus.publish(CommentaryDirectiveIssued(directive=directive))
        return directives

    def handle_replay_change(self, state, transition: str) -> list[CommentaryDirective]:
        """Decide and publish directives for a replay transition."""
        with self._lock:
            # Always track replay state (so live/replay is correct once casting
            # starts), but don't voice anything while the desk is still gated.
            self._replay_active = bool(getattr(state, "active", False))
            if not self._casting_open():
                return []
            directives = self._decide_replay(state, transition)
            for directive in directives:
                self._record(directive)
        for directive in directives:
            self._bus.publish(CommentaryDirectiveIssued(directive=directive))
        return directives

    # ------------------------------------------------------------------ #
    # Internal decision logic (called under lock)
    # ------------------------------------------------------------------ #
    def _decide_match_event(self, event: MatchEvent) -> list[CommentaryDirective]:
        speaker = policy.speaker_for_event(event)
        if speaker is Speaker.NONE:
            return []  # covered by another event; stay silent without ceremony

        priority = policy.priority_for_event(event)

        # Replay enforcement: never let play-by-play describe replay as live.
        if speaker is Speaker.PLAY_BY_PLAY and not self._live_now():
            return [
                CommentaryDirective(
                    speaker=Speaker.NONE,
                    kind=DirectiveKind.SILENCE,
                    priority=DirectivePriority.AMBIENT,
                    excitement=0.0,
                    topic=policy.topic_for_event(event),
                    reason="replay_active",
                )
            ]

        now = self._clock()
        interrupt = False
        if now < self._speaking_until:
            # Mic is busy: interrupt only for a strictly higher priority when
            # interruptions are allowed; otherwise yield silently (no talk-over).
            if priority > self._current_priority and self._allow_interruptions:
                interrupt = True
            else:
                return []

        excitement = policy.excitement_for_event(
            event,
            round_importance=self._round_importance,
            series_importance=self._series_importance,
            baseline=self._baseline,
            contrast=self._contrast,
        )
        kind = DirectiveKind.CALL if speaker is Speaker.PLAY_BY_PLAY else DirectiveKind.ANALYZE
        primary = CommentaryDirective(
            speaker=speaker,
            kind=kind,
            priority=priority,
            excitement=excitement,
            topic=policy.topic_for_event(event),
            interrupt=interrupt,
            context=self._with_team_names(policy.context_for_event(event)),
        )
        self._occupy_mic(priority, speaker, now)

        directives = [primary]
        # After a round is called, hand the mic to the analyst.
        if isinstance(event, RoundEnded):
            directives.append(
                CommentaryDirective(
                    speaker=Speaker.ANALYST,
                    kind=DirectiveKind.HANDOFF,
                    priority=DirectivePriority.LOW,
                    excitement=round(excitement * 0.6, 4),
                    topic="round_analysis",
                    reason="post_round_handoff",
                    context=self._with_team_names(policy.context_for_event(event)),
                )
            )
        # Live banter beat: on a marquee play-by-play call (e.g. a clutch), let the
        # analyst chime in with a short reaction so the desk sounds like a real
        # two-person booth. Low priority + non-interrupting, so it never steps on
        # live action; it simply follows once the caller's line has landed.
        elif (
            speaker is Speaker.PLAY_BY_PLAY
            and isinstance(event, ClutchWon)
            and excitement >= _BANTER_EXCITEMENT
        ):
            directives.append(
                CommentaryDirective(
                    speaker=Speaker.ANALYST,
                    kind=DirectiveKind.HANDOFF,
                    priority=DirectivePriority.LOW,
                    excitement=round(excitement * 0.7, 4),
                    topic="reaction",
                    reason="banter_reaction",
                    context=self._with_team_names(policy.context_for_event(event)),
                )
            )
        return directives

    def _decide_replay(self, state, transition: str) -> list[CommentaryDirective]:
        now = self._clock()
        if transition == "started":
            replay_type = getattr(state, "replay_type", ReplayType.GENERIC)
            excitement = 0.7 if replay_type in (ReplayType.CLUTCH, ReplayType.MULTIKILL) else 0.5
            self._occupy_mic(DirectivePriority.NORMAL, Speaker.ANALYST, now)
            return [
                CommentaryDirective(
                    speaker=Speaker.ANALYST,
                    kind=DirectiveKind.REPLAY_ANALYZE,
                    priority=DirectivePriority.NORMAL,
                    excitement=excitement,
                    topic="replay",
                    interrupt=self._allow_interruptions,
                    reason=f"replay_{replay_type}",
                    context={
                        "replay_type": str(replay_type),
                        "speed": getattr(state, "speed", 1.0),
                    },
                )
            ]
        if transition == "ended":
            self._current_priority = DirectivePriority.AMBIENT
            self._speaking_until = now
            return [
                CommentaryDirective(
                    speaker=Speaker.PLAY_BY_PLAY,
                    kind=DirectiveKind.REPLAY_RETURN,
                    priority=DirectivePriority.LOW,
                    excitement=round(0.4 * (0.6 + 0.4 * self._baseline), 4),
                    topic="back_to_live",
                    reason="replay_ended",
                )
            ]
        # Speed change: just track state, no new talk.
        return []

    # ------------------------------------------------------------------ #
    def _team(self, side_label: str | None) -> str:
        if side_label == "CT":
            return self._ct_name
        if side_label == "T":
            return self._t_name
        return side_label or ""

    def _with_team_names(self, context: dict) -> dict:
        """Add team-name facts so commentary can use them instead of CT/T.

        Always exposes ``ct_team``/``t_team``; maps any winner/side in the context
        to its team name (``winner_team``/``side_team``). When GSI has no real names
        these are just "CT"/"T", so nothing changes.
        """
        context["ct_team"] = self._ct_name
        context["t_team"] = self._t_name
        winner = context.get("winner")
        if winner in ("CT", "T"):
            context["winner_team"] = self._team(winner)
        side = context.get("side")
        if side in ("CT", "T"):
            context["side_team"] = self._team(side)
        return context

    def _casting_open(self) -> bool:
        """Whether the cast-start gate (if any) has cleared the desk to talk."""
        return self._cast_gate is None or self._cast_gate.is_open

    def _live_now(self) -> bool:
        return policy.is_live_broadcast(
            replay_active=self._replay_active,
            replay_integration_enabled=self._replay_enabled,
            vision_suggests_replay=self._vision_replay,
            treat_unknown_as_live=self._treat_unknown_as_live,
        )

    def _occupy_mic(self, priority: DirectivePriority, speaker: Speaker, now: float) -> None:
        self._current_priority = priority
        self._current_speaker = speaker
        # The configured minimum gap acts as a floor, so consecutive directives
        # are never packed closer than the operator allows (rate limiting).
        window = policy.SPEAKING_WINDOW_SECONDS.get(priority, 2.0)
        self._speaking_until = now + max(window, self._min_gap)

    def _record(self, directive: CommentaryDirective) -> None:
        self._recent.append(directive)
        _log.debug(
            "Directive: %s/%s p=%s excite=%.2f topic=%s interrupt=%s%s",
            directive.speaker,
            directive.kind,
            directive.priority,
            directive.excitement,
            directive.topic,
            directive.interrupt,
            f" reason={directive.reason}" if directive.reason else "",
        )
