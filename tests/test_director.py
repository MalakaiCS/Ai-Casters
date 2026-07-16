"""Tests for the Commentary Director's decisions."""

from __future__ import annotations

from ai_caster.core.events import EventBus
from ai_caster.detection.events import (
    ClutchWon,
    Kill,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)
from ai_caster.director.directives import (
    CommentaryDirectiveIssued,
    DirectiveKind,
    Speaker,
)
from ai_caster.director.director import CommentaryDirector
from ai_caster.replay.models import ReplayState, ReplayType


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _director(clock=None, **kwargs) -> tuple[CommentaryDirector, list, EventBus]:
    bus = EventBus()
    issued: list[CommentaryDirectiveIssued] = []
    bus.subscribe(CommentaryDirectiveIssued, issued.append)
    director = CommentaryDirector(bus, clock=clock or _Clock(), **kwargs)
    return director, issued, bus


def test_kill_routes_to_play_by_play():
    director, issued, _ = _director()
    directives = director.handle_match_event(Kill(killer_name="a", victim_name="b"))
    assert len(directives) == 1
    assert directives[0].speaker is Speaker.PLAY_BY_PLAY
    assert directives[0].kind is DirectiveKind.CALL
    assert len(issued) == 1  # published on the bus


def test_round_started_routes_to_analyst():
    director, _, _ = _director()
    directives = director.handle_match_event(RoundStarted())
    assert directives[0].speaker is Speaker.ANALYST
    assert directives[0].kind is DirectiveKind.ANALYZE


def test_score_changed_is_silent():
    director, issued, _ = _director()
    assert director.handle_match_event(ScoreChanged()) == []
    assert issued == []


def test_round_ended_hands_off_to_analyst():
    director, _, _ = _director()
    directives = director.handle_match_event(RoundEnded(winner="CT", reason="elimination"))
    kinds = [(d.speaker, d.kind) for d in directives]
    assert (Speaker.PLAY_BY_PLAY, DirectiveKind.CALL) in kinds
    assert (Speaker.ANALYST, DirectiveKind.HANDOFF) in kinds


def test_higher_priority_interrupts_current_speech():
    clock = _Clock()
    director, _, _ = _director(clock=clock)
    director.handle_match_event(Kill(is_entry=True))  # HIGH, occupies the mic
    # Immediately, a clutch win (CRITICAL) should interrupt.
    directives = director.handle_match_event(ClutchWon(player_name="hero"))
    # The play-by-play call interrupts; a low-priority analyst banter beat follows.
    primary = directives[0]
    assert primary.speaker is Speaker.PLAY_BY_PLAY
    assert primary.interrupt is True


def test_clutch_win_triggers_analyst_banter_reaction():
    clock = _Clock()
    director, _, _ = _director(clock=clock)
    directives = director.handle_match_event(ClutchWon(player_name="hero"))
    reactions = [
        d for d in directives if d.speaker is Speaker.ANALYST and d.reason == "banter_reaction"
    ]
    assert len(reactions) == 1
    beat = reactions[0]
    assert beat.topic == "reaction"
    assert beat.interrupt is False  # never steps on the caller


def test_equal_or_lower_priority_yields_while_busy():
    clock = _Clock()
    director, _, _ = _director(clock=clock)
    director.handle_match_event(Kill(is_entry=True))  # HIGH
    clock.advance(0.1)
    # A normal kill while the mic is busy with higher priority -> silence.
    assert director.handle_match_event(Kill()) == []


def test_min_gap_floor_rate_limits():
    clock = _Clock()
    director, _, _ = _director(clock=clock, min_speech_gap=5.0)
    director.handle_match_event(Kill())  # NORMAL, window floored to 5s
    clock.advance(3.0)  # past the 2.5s normal window but within the 5s floor
    assert director.handle_match_event(Kill()) == []


def test_interruptions_can_be_disabled():
    clock = _Clock()
    director, _, _ = _director(clock=clock, allow_interruptions=False)
    director.handle_match_event(Kill(is_entry=True))  # HIGH
    directives = director.handle_match_event(ClutchWon())  # CRITICAL but no interrupts
    assert directives == []  # yields instead of interrupting


def test_replay_active_suppresses_live_play_by_play():
    director, _, _ = _director()
    director.handle_replay_change(ReplayState(active=True, replay_type=ReplayType.KILL), "started")
    assert director.replay_active is True
    assert director.is_live is False
    # A live-action kill during replay must never be called as live.
    directives = director.handle_match_event(Kill(killer_name="a"))
    assert len(directives) == 1
    assert directives[0].is_silence is True
    assert directives[0].reason == "replay_active"


def test_vision_replay_hint_used_only_when_integration_disabled():
    from ai_caster.vision.events import VisionStateUpdated
    from ai_caster.vision.observations import ObservationKind, SceneType, VisionObservation
    from ai_caster.vision.state import VisionState

    def replay_vision(confidence: float) -> VisionState:
        return VisionState.from_observations(
            0,
            [VisionObservation(ObservationKind.SCENE, confidence, 0, value=SceneType.REPLAY.value)],
            min_confidence=0.5,
        )

    # Integration disabled + cautious safety flag: a confident vision replay
    # banner makes the broadcast "not live".
    director, _, bus = _director(replay_integration_enabled=False, treat_unknown_as_live=False)
    bus.publish(VisionStateUpdated(state=replay_vision(0.8)))
    assert director.is_live is False
    # A weak reading is ignored.
    bus.publish(VisionStateUpdated(state=replay_vision(0.3)))
    assert director.is_live is True

    # With integration enabled, the vision hint never overrides "live".
    director2, _, bus2 = _director(replay_integration_enabled=True)
    bus2.publish(VisionStateUpdated(state=replay_vision(0.9)))
    assert director2.is_live is True


def test_replay_started_and_ended_directives():
    director, _, _ = _director()
    started = director.handle_replay_change(
        ReplayState(active=True, replay_type=ReplayType.CLUTCH), "started"
    )
    assert started[0].kind is DirectiveKind.REPLAY_ANALYZE
    assert started[0].speaker is Speaker.ANALYST

    ended = director.handle_replay_change(ReplayState(active=False), "ended")
    assert ended[0].kind is DirectiveKind.REPLAY_RETURN
    assert director.is_live is True


def test_excitement_uses_round_importance_from_model():
    from ai_caster.gsi.models import GameState
    from ai_caster.match.events import MatchModelUpdated
    from ai_caster.match.model import build_live_match
    from tests.conftest import make_player, make_state

    director, _, bus = _director()
    # A match-point model lifts round importance and therefore excitement.
    live = build_live_match(
        GameState.model_validate(make_state([make_player("1", "a", "CT")], ct_score=12)),
        rounds_to_win=13,
    )
    bus.publish(MatchModelUpdated(match=live))
    directives = director.handle_match_event(Kill())
    assert directives[0].excitement > 0.5


def test_configure_updates_tone_and_pacing_live():
    director, _issued, _ = _director(
        baseline_excitement=0.5, allow_interruptions=True, min_speech_gap=0.8
    )
    director.configure(baseline_excitement=0.9, allow_interruptions=False, min_speech_gap=1.5)
    assert director._baseline == 0.9
    assert director._allow_interruptions is False
    assert director._min_gap == 1.5
    # Partial updates leave other values untouched.
    director.configure(baseline_excitement=0.2)
    assert director._baseline == 0.2
    assert director._min_gap == 1.5


def test_configure_updates_excitement_contrast():
    director, _issued, _ = _director(excitement_contrast=0.1)
    assert director._contrast == 0.1
    director.configure(excitement_contrast=0.8)
    assert director._contrast == 0.8
