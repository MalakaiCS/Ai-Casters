"""Broadcast-flow policy — pure decision helpers.

These map match events to a speaker, priority, excitement and topic, and resolve
whether the broadcast is currently live. Keeping them pure and free of state
makes the Director's behaviour easy to reason about and exhaustively testable.
"""

from __future__ import annotations

from ai_caster.detection.events import (
    BombDefused,
    BombExploded,
    BombPlanted,
    ClutchStarted,
    ClutchWon,
    Kill,
    KnifeRound,
    MatchEnded,
    MatchEvent,
    MatchStarted,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)
from ai_caster.director.directives import DirectivePriority, Speaker


def side_selection_note(best_of: int) -> str:
    """How the starting side is decided for this format — plain English for casters."""
    if best_of == 1:
        return "the knife round decides which side each team starts on"
    if best_of >= 3:
        return "the team that didn't pick this map chooses which side to start"
    return ""

# How long a directive of each priority is assumed to occupy the mic. Used for
# interrupt/rate-limit decisions (a rough speaking-time budget, in seconds).
SPEAKING_WINDOW_SECONDS: dict[DirectivePriority, float] = {
    DirectivePriority.AMBIENT: 0.0,
    DirectivePriority.LOW: 3.5,
    DirectivePriority.NORMAL: 2.5,
    DirectivePriority.HIGH: 2.0,
    DirectivePriority.CRITICAL: 3.0,
}

# Events the play-by-play caller owns (fast, live action).
_PBP_EVENTS = (Kill, BombPlanted, BombDefused, BombExploded, ClutchStarted, ClutchWon, MatchEnded)
# Events the analyst owns (setup, context, narrative).
_ANALYST_EVENTS = (RoundStarted, MatchStarted, KnifeRound)


def speaker_for_event(event: MatchEvent) -> Speaker:
    """Which role should speak to this event (``NONE`` = no one)."""
    if isinstance(event, RoundEnded):
        return Speaker.PLAY_BY_PLAY  # PBP calls the result, then hands off
    if isinstance(event, _PBP_EVENTS):
        return Speaker.PLAY_BY_PLAY
    if isinstance(event, _ANALYST_EVENTS):
        return Speaker.ANALYST
    # ScoreChanged / PlayerDeath are covered by RoundEnded / Kill -> stay silent.
    return Speaker.NONE


def priority_for_event(event: MatchEvent) -> DirectivePriority:
    """Broadcast priority of an event."""
    if isinstance(event, (ClutchWon, MatchEnded)):
        return DirectivePriority.CRITICAL
    if isinstance(event, (ClutchStarted, BombDefused, BombExploded, BombPlanted)):
        return DirectivePriority.HIGH
    if isinstance(event, Kill):
        return DirectivePriority.HIGH if event.is_entry else DirectivePriority.NORMAL
    if isinstance(event, RoundEnded):
        return DirectivePriority.NORMAL
    if isinstance(event, (RoundStarted, MatchStarted, KnifeRound)):
        return DirectivePriority.LOW
    return DirectivePriority.AMBIENT


_BASE_EXCITEMENT: dict[type, float] = {
    ClutchWon: 1.0,
    MatchEnded: 1.0,
    BombDefused: 0.85,
    ClutchStarted: 0.8,
    BombExploded: 0.8,
    BombPlanted: 0.7,
    RoundEnded: 0.55,
    RoundStarted: 0.3,
    MatchStarted: 0.4,
    KnifeRound: 0.5,
}


def base_excitement_for_event(event: MatchEvent) -> float:
    """The intrinsic excitement of an event before context scaling."""
    if isinstance(event, Kill):
        value = 0.5
        if event.is_entry:
            value += 0.15
        if event.headshot:
            value += 0.1
        if event.is_trade:
            value += 0.05
        return min(value, 1.0)
    for event_type, value in _BASE_EXCITEMENT.items():
        if isinstance(event, event_type):
            return value
    return 0.2


def excitement_for_event(
    event: MatchEvent,
    *,
    round_importance: float = 0.0,
    series_importance: float = 0.0,
    baseline: float = 0.7,
    contrast: float = 0.0,
) -> float:
    """Final excitement in ``[0, 1]``.

    Combines four signals so the caller reacts *proportionally to how big the
    moment is* — the whole point of "hype the game-defining plays, stay calm on
    the minor ones":

    * **intrinsic** — the event's own weight (an ace >> a mid-round trade).
    * **contrast** — reshapes the intrinsic value so a higher setting widens the
      gap between minor and defining plays (minor plays get calmer, huge plays
      stay peaked); ``0`` is linear (backward-compatible).
    * **stakes** — the bigger of round/series importance lifts everything, so the
      same play is called harder at match/series point than in an early round.
    * **baseline** — the operator's overall energy.
    """
    base = base_excitement_for_event(event)
    # contrast 0 -> gamma 1 (linear); contrast 1 -> gamma 3 (steep dynamic range).
    gamma = 1.0 + 2.0 * max(0.0, min(contrast, 1.0))
    shaped = base**gamma
    stakes = max(round_importance, series_importance)
    lifted = shaped + 0.25 * stakes
    scaled = lifted * (0.6 + 0.4 * baseline)
    return round(max(0.0, min(scaled, 1.0)), 4)


def topic_for_event(event: MatchEvent) -> str:
    """A short machine topic label for the event."""
    if isinstance(event, KnifeRound):
        return "knife_round"
    return type(event).__name__


def context_for_event(event: MatchEvent) -> dict:
    """Facts the word-generating AIs (M6) need, extracted from the event."""
    context: dict = {"round": event.round_number + 1}
    if isinstance(event, Kill):
        context.update(
            killer=event.killer_name,
            victim=event.victim_name,
            weapon=event.weapon,
            headshot=event.headshot,
            entry=event.is_entry,
            trade=event.is_trade,
        )
    elif isinstance(event, (ClutchStarted, ClutchWon)):
        context.update(
            player=event.player_name,
            side=event.player_side,
            opponents=getattr(event, "opponents_alive", getattr(event, "opponents_beaten", 0)),
        )
    elif isinstance(event, RoundEnded):
        context.update(winner=event.winner, reason=event.reason, bomb_planted=event.bomb_planted)
    elif isinstance(event, MatchStarted):
        context.update(map=event.map_name, best_of=event.best_of)
        note = side_selection_note(event.best_of)
        if note:
            context["side_selection"] = note
    elif isinstance(event, KnifeRound):
        context["side_rule"] = "the winner chooses which side to start on"
    elif isinstance(event, MatchEnded):
        context.update(winner=event.winner, ct_score=event.ct_score, t_score=event.t_score)
    elif isinstance(event, ScoreChanged):
        context.update(ct_score=event.ct_score, t_score=event.t_score)
    return context


def is_live_broadcast(
    *,
    replay_active: bool,
    replay_integration_enabled: bool,
    vision_suggests_replay: bool,
    treat_unknown_as_live: bool,
) -> bool:
    """Resolve whether the broadcast is live (so PBP may call live action).

    - An **authoritative** active replay (from the external replay system) always
      means *not live*.
    - With replay integration enabled and no active replay, it is live.
    - With replay integration **disabled**, replay state is unknown; fall back to
      the vision hint and the ``treat_unknown_as_live`` safety setting.
    """
    if replay_active:
        return False
    if replay_integration_enabled:
        return True
    if vision_suggests_replay:
        return treat_unknown_as_live
    return True
