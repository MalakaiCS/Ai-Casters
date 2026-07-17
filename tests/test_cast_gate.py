"""Tests for the cast-start gate (ASAP / knife round / round 1)."""

from __future__ import annotations

from ai_caster.config.models import CastStart
from ai_caster.core.events import EventBus
from ai_caster.detection.events import KnifeRound, MatchStarted, RoundEnded, RoundStarted
from ai_caster.director.cast_gate import CastGate


def _gate(mode: CastStart) -> tuple[CastGate, EventBus]:
    bus = EventBus()
    return CastGate(bus, mode=mode), bus


# --- ASAP ------------------------------------------------------------------ #
def test_asap_is_open_from_the_start():
    gate, _ = _gate(CastStart.ASAP)
    assert gate.is_open


# --- knife round ----------------------------------------------------------- #
def test_knife_mode_closed_until_knife_round():
    gate, bus = _gate(CastStart.KNIFE_ROUND)
    assert not gate.is_open
    bus.publish(MatchStarted(map_name="de_dust2"))
    assert not gate.is_open  # warm-up / match start doesn't open it
    bus.publish(KnifeRound(round_number=0))
    assert gate.is_open


def test_knife_mode_opens_at_first_round_when_no_knife():
    gate, bus = _gate(CastStart.KNIFE_ROUND)
    bus.publish(MatchStarted(map_name="de_dust2"))
    bus.publish(RoundStarted(round_number=1))  # no knife round in this match
    assert gate.is_open


# --- round 1 --------------------------------------------------------------- #
def test_round1_mode_skips_knife_round():
    gate, bus = _gate(CastStart.ROUND_1)
    bus.publish(MatchStarted(map_name="de_dust2"))
    # Knife round: KnifeRound then its RoundStarted (same tick order) -> still closed.
    bus.publish(KnifeRound(round_number=0))
    bus.publish(RoundStarted(round_number=0))
    assert not gate.is_open
    # The first real round opens it.
    bus.publish(RoundStarted(round_number=1))
    assert gate.is_open


def test_round1_mode_opens_at_first_round_without_knife():
    gate, bus = _gate(CastStart.ROUND_1)
    bus.publish(MatchStarted(map_name="de_dust2"))
    bus.publish(RoundStarted(round_number=1))  # no knife round played
    assert gate.is_open


# --- lifecycle ------------------------------------------------------------- #
def test_new_match_rearms_the_gate():
    gate, bus = _gate(CastStart.ROUND_1)
    bus.publish(RoundStarted(round_number=1))
    assert gate.is_open
    # A brand-new match must close the gate again for round-1 mode.
    bus.publish(MatchStarted(map_name="de_inferno"))
    assert not gate.is_open


def test_set_mode_to_asap_opens_immediately():
    gate, _ = _gate(CastStart.ROUND_1)
    assert not gate.is_open
    gate.set_mode(CastStart.ASAP)
    assert gate.is_open


def test_switching_mode_does_not_silence_a_running_desk():
    gate, bus = _gate(CastStart.KNIFE_ROUND)
    bus.publish(KnifeRound(round_number=0))
    assert gate.is_open
    gate.set_mode(CastStart.ROUND_1)  # changed mid-match
    assert gate.is_open  # stays open — never cut the casters off


def test_dispose_stops_reacting():
    gate, bus = _gate(CastStart.KNIFE_ROUND)
    gate.dispose()
    bus.publish(KnifeRound(round_number=0))
    assert not gate.is_open


# --- integration with the director ----------------------------------------- #
def test_director_stays_silent_until_gate_opens():
    from ai_caster.director.directives import CommentaryDirectiveIssued
    from ai_caster.director.director import CommentaryDirector

    bus = EventBus()
    gate = CastGate(bus, mode=CastStart.ROUND_1)  # subscribed first
    director = CommentaryDirector(bus, cast_gate=gate)
    issued: list = []
    bus.subscribe(CommentaryDirectiveIssued, issued.append)

    # A round ends during the knife round window -> nothing cast.
    director.handle_match_event(RoundEnded(round_number=0, winner="CT"))
    assert issued == []

    # Round 1 begins; now the desk is cleared and events are cast.
    bus.publish(RoundStarted(round_number=1))
    assert gate.is_open
    director.handle_match_event(RoundEnded(round_number=1, winner="T"))
    assert issued  # directives now flow

    director.dispose()
    gate.dispose()
