"""Tests for the pure broadcast-flow policy helpers."""

from __future__ import annotations

from ai_caster.detection.events import (
    ClutchWon,
    Kill,
    MatchStarted,
    PlayerDeath,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)
from ai_caster.director import policy
from ai_caster.director.directives import DirectivePriority, Speaker


def test_speaker_routing():
    assert policy.speaker_for_event(Kill()) is Speaker.PLAY_BY_PLAY
    assert policy.speaker_for_event(ClutchWon()) is Speaker.PLAY_BY_PLAY
    assert policy.speaker_for_event(RoundEnded()) is Speaker.PLAY_BY_PLAY
    assert policy.speaker_for_event(RoundStarted()) is Speaker.ANALYST
    assert policy.speaker_for_event(MatchStarted()) is Speaker.ANALYST
    # Covered by other events -> nobody speaks.
    assert policy.speaker_for_event(ScoreChanged()) is Speaker.NONE
    assert policy.speaker_for_event(PlayerDeath()) is Speaker.NONE


def test_priority_ordering():
    assert policy.priority_for_event(ClutchWon()) is DirectivePriority.CRITICAL
    assert policy.priority_for_event(Kill(is_entry=True)) is DirectivePriority.HIGH
    assert policy.priority_for_event(Kill()) is DirectivePriority.NORMAL
    assert policy.priority_for_event(RoundStarted()) is DirectivePriority.LOW


def test_excitement_scales_with_importance_and_baseline():
    low = policy.excitement_for_event(Kill(), round_importance=0.0, baseline=0.5)
    high = policy.excitement_for_event(Kill(), round_importance=1.0, baseline=1.0)
    assert 0.0 <= low <= high <= 1.0
    assert high > low
    # A clutch win is always more exciting than a plain kill at equal context.
    assert policy.excitement_for_event(ClutchWon()) > policy.excitement_for_event(Kill())


def test_context_extracts_event_facts():
    ctx = policy.context_for_event(Kill(round_number=4, killer_name="alice", victim_name="bob"))
    assert ctx["round"] == 5
    assert ctx["killer"] == "alice"
    assert ctx["victim"] == "bob"


def test_is_live_broadcast_rules():
    # Authoritative active replay -> never live.
    assert (
        policy.is_live_broadcast(
            replay_active=True,
            replay_integration_enabled=True,
            vision_suggests_replay=False,
            treat_unknown_as_live=True,
        )
        is False
    )
    # Integration enabled, no replay -> live.
    assert (
        policy.is_live_broadcast(
            replay_active=False,
            replay_integration_enabled=True,
            vision_suggests_replay=True,
            treat_unknown_as_live=False,
        )
        is True
    )
    # Integration disabled + vision hints replay -> governed by the safety flag.
    assert (
        policy.is_live_broadcast(
            replay_active=False,
            replay_integration_enabled=False,
            vision_suggests_replay=True,
            treat_unknown_as_live=False,
        )
        is False
    )
    assert (
        policy.is_live_broadcast(
            replay_active=False,
            replay_integration_enabled=False,
            vision_suggests_replay=True,
            treat_unknown_as_live=True,
        )
        is True
    )
