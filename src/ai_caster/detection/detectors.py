"""GSI-based event detector.

Detects match events by diffing consecutive parsed GSI payloads. The detector is
**stateful**: it remembers the previous tick, per-round bookkeeping (first blood,
active clutch) and a short window of recent deaths so it can classify entries and
trades. It resets its per-round state whenever a new round goes live.

Design constraints honoured here:
- GSI gives cumulative per-player kills/deaths and current health, but does not
  link a killer to a victim. We detect deaths reliably (health -> 0) and credit
  kills to the player whose cumulative kill count rose; killer/victim are paired
  only when a tick is unambiguous. Vision (M4) supplies reliable pairing.
- No fact is invented: uncertain inferences carry a sub-1.0 ``confidence``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ai_caster.core.logging import get_logger
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
    PlayerDeath,
    RoundEnded,
    RoundStarted,
    ScoreChanged,
)
from ai_caster.gsi.models import GameState

_log = get_logger("detection")

TRADE_WINDOW_SECONDS = 5.0


@dataclass
class _PlayerTick:
    steamid: str
    name: str
    side: str | None
    health: int
    kills: int
    deaths: int
    killhs: int


def _extract(state: GameState) -> dict[str, _PlayerTick]:
    """Flatten a GSI payload into per-steamid tick data for diffing."""
    ticks: dict[str, _PlayerTick] = {}
    source = state.allplayers or {}
    if not source and state.player is not None and state.player.steamid:
        source = {state.player.steamid: state.player}
    for steamid, player in source.items():
        st = player.state
        ms = player.match_stats
        ticks[steamid] = _PlayerTick(
            steamid=steamid,
            name=player.name or "unknown",
            side=player.team,
            health=(st.health if st and st.health is not None else 0),
            kills=(ms.kills if ms and ms.kills is not None else 0),
            deaths=(ms.deaths if ms and ms.deaths is not None else 0),
            killhs=(st.round_killhs if st and st.round_killhs is not None else 0),
        )
    return ticks


class EventDetector:
    """Turns a stream of GSI payloads into a stream of :class:`MatchEvent`."""

    def __init__(self, trade_window: float = TRADE_WINDOW_SECONDS) -> None:
        self._trade_window = trade_window
        self._prev: GameState | None = None
        self._match_started = False
        self._knife_round_done = False
        # Per-round state.
        self._round_number = -1
        self._first_blood_done = False
        self._recent_deaths: list[tuple[float, str, str | None]] = []  # (ts, steamid, side)
        self._clutch_side: str | None = None
        self._clutch_player: tuple[str, str] | None = None  # (steamid, name)
        self._clutch_opponents = 0

    # ------------------------------------------------------------------ #
    def detect(self, state: GameState) -> list[MatchEvent]:
        """Diff ``state`` against the previous payload and return new events."""
        prev = self._prev
        events: list[MatchEvent] = []
        round_number = state.round_number or 0
        now = self._timestamp(state)

        if prev is None:
            self._prev = state
            self._maybe_match_started(state, events, round_number)
            self._maybe_knife_round(state, events, round_number)
            return events

        self._maybe_match_started(state, events, round_number)
        self._maybe_knife_round(state, events, round_number)
        self._detect_round_transitions(prev, state, events, round_number)
        self._detect_bomb(prev, state, events, round_number)
        self._detect_kills_and_deaths(prev, state, events, round_number, now)
        self._detect_clutch(state, events, round_number)
        self._detect_score(prev, state, events, round_number)
        self._maybe_match_ended(prev, state, events, round_number)

        self._prune_recent_deaths(now)
        self._prev = state
        return events

    # ------------------------------------------------------------------ #
    # Match phase
    # ------------------------------------------------------------------ #
    def _maybe_match_started(self, state: GameState, events: list, rnd: int) -> None:
        phase = state.map.phase if state.map else None
        if not self._match_started and phase in {"live", "warmup"} and state.map_name:
            self._match_started = True
            events.append(
                MatchStarted(
                    round_number=rnd,
                    map_name=state.map_name,
                    best_of=_best_of(state),
                )
            )

    def _maybe_knife_round(self, state: GameState, events: list, rnd: int) -> None:
        """Announce the knife round once — it decides which side teams start on."""
        if self._knife_round_done:
            return
        phase = state.round.phase if state.round else None
        if phase != "live" or not is_knife_round(state):
            return
        self._knife_round_done = True
        events.append(KnifeRound(round_number=rnd))

    def _maybe_match_ended(self, prev: GameState, state: GameState, events: list, rnd: int) -> None:
        prev_phase = prev.map.phase if prev.map else None
        phase = state.map.phase if state.map else None
        if phase == "gameover" and prev_phase != "gameover":
            ct = state.ct_score or 0
            t = state.t_score or 0
            winner = "CT" if ct > t else "T" if t > ct else None
            events.append(MatchEnded(round_number=rnd, winner=winner, ct_score=ct, t_score=t))

    # ------------------------------------------------------------------ #
    # Rounds
    # ------------------------------------------------------------------ #
    def _detect_round_transitions(
        self, prev: GameState, state: GameState, events: list, rnd: int
    ) -> None:
        prev_phase = prev.round.phase if prev.round else None
        phase = state.round.phase if state.round else None

        # Round goes live -> reset per-round bookkeeping and announce start.
        if phase == "live" and prev_phase != "live":
            self._reset_round_state(rnd)
            events.append(RoundStarted(round_number=rnd))

        # Round ends.
        if phase == "over" and prev_phase == "live":
            winner = state.round.win_team if state.round else None
            bomb = state.round.bomb if state.round else None
            reason = self._round_reason(winner, bomb)
            bomb_planted = bomb in {"planted", "defused", "exploded"}
            events.append(
                RoundEnded(
                    round_number=rnd,
                    winner=winner,
                    reason=reason,
                    bomb_planted=bomb_planted,
                )
            )
            # Resolve a pending clutch.
            if self._clutch_side and winner == self._clutch_side and self._clutch_player:
                steamid, name = self._clutch_player
                events.append(
                    ClutchWon(
                        round_number=rnd,
                        player_steamid=steamid,
                        player_name=name,
                        player_side=self._clutch_side,
                        opponents_beaten=self._clutch_opponents,
                    )
                )

    @staticmethod
    def _round_reason(winner: str | None, bomb: str | None) -> str:
        if bomb == "exploded":
            return "bomb_exploded"
        if bomb == "defused":
            return "bomb_defused"
        if winner in {"CT", "T"}:
            return "elimination"
        return "unknown"

    def _reset_round_state(self, rnd: int) -> None:
        self._round_number = rnd
        self._first_blood_done = False
        self._recent_deaths.clear()
        self._clutch_side = None
        self._clutch_player = None
        self._clutch_opponents = 0

    # ------------------------------------------------------------------ #
    # Bomb
    # ------------------------------------------------------------------ #
    def _detect_bomb(self, prev: GameState, state: GameState, events: list, rnd: int) -> None:
        prev_bomb = prev.round.bomb if prev.round else None
        bomb = state.round.bomb if state.round else None
        if bomb == prev_bomb:
            return
        if bomb == "planted":
            events.append(BombPlanted(round_number=rnd))
        elif bomb == "defused":
            events.append(BombDefused(round_number=rnd))
        elif bomb == "exploded":
            events.append(BombExploded(round_number=rnd))

    # ------------------------------------------------------------------ #
    # Kills & deaths
    # ------------------------------------------------------------------ #
    def _detect_kills_and_deaths(
        self, prev: GameState, state: GameState, events: list, rnd: int, now: float
    ) -> None:
        prev_ticks = _extract(prev)
        ticks = _extract(state)

        deaths: list[_PlayerTick] = []
        killers: list[tuple[_PlayerTick, int, int]] = []  # (tick, kill_delta, hs_delta)

        for steamid, cur in ticks.items():
            old = prev_ticks.get(steamid)
            if old is None:
                continue
            # Death: health crossed to zero.
            if old.health > 0 and cur.health <= 0:
                deaths.append(cur)
            # Kill(s): cumulative kill count rose.
            kill_delta = cur.kills - old.kills
            if kill_delta > 0:
                killers.append((cur, kill_delta, max(0, cur.killhs - old.killhs)))

        # Emit deaths and remember them for trade classification.
        for victim in deaths:
            self._recent_deaths.append((now, victim.steamid, victim.side))
            events.append(
                PlayerDeath(
                    round_number=rnd,
                    victim_steamid=victim.steamid,
                    victim_name=victim.name,
                    victim_side=victim.side,
                )
            )

        # Pair killer<->victim only when a tick is unambiguous.
        single_victim = deaths[0] if len(deaths) == 1 else None
        total_kill_delta = sum(delta for _, delta, _ in killers)

        for killer, delta, hs_delta in killers:
            is_entry = False
            if not self._first_blood_done:
                self._first_blood_done = True
                is_entry = True
            is_trade = self._is_trade(killer, now)
            paired = single_victim if (total_kill_delta == 1 and single_victim) else None
            headshot = delta == 1 and hs_delta == 1
            events.append(
                Kill(
                    round_number=rnd,
                    killer_steamid=killer.steamid,
                    killer_name=killer.name,
                    killer_side=killer.side,
                    victim_steamid=(paired.steamid if paired else None),
                    victim_name=(paired.name if paired else None),
                    headshot=headshot,
                    is_entry=is_entry,
                    is_trade=is_trade,
                    # Unpaired kills are slightly less certain about victim/detail.
                    confidence=1.0 if paired else 0.85,
                )
            )

    def _is_trade(self, killer: _PlayerTick, now: float) -> bool:
        """A kill is a trade if a *teammate* of the killer died within the trade
        window (the killer is avenging that death)."""
        for ts, _steamid, side in self._recent_deaths:
            if side == killer.side and (now - ts) <= self._trade_window:
                return True
        return False

    def _prune_recent_deaths(self, now: float) -> None:
        self._recent_deaths = [
            entry for entry in self._recent_deaths if (now - entry[0]) <= self._trade_window
        ]

    # ------------------------------------------------------------------ #
    # Clutch
    # ------------------------------------------------------------------ #
    def _detect_clutch(self, state: GameState, events: list, rnd: int) -> None:
        if self._clutch_side is not None:
            return  # already tracking a clutch this round
        if (state.round.phase if state.round else None) != "live":
            return
        ticks = _extract(state)
        alive_ct = [t for t in ticks.values() if t.side == "CT" and t.health > 0]
        alive_t = [t for t in ticks.values() if t.side == "T" and t.health > 0]
        for lone, opponents, side in ((alive_ct, alive_t, "CT"), (alive_t, alive_ct, "T")):
            if len(lone) == 1 and len(opponents) >= 2:
                player = lone[0]
                self._clutch_side = side
                self._clutch_player = (player.steamid, player.name)
                self._clutch_opponents = len(opponents)
                events.append(
                    ClutchStarted(
                        round_number=rnd,
                        player_steamid=player.steamid,
                        player_name=player.name,
                        player_side=side,
                        opponents_alive=len(opponents),
                    )
                )
                return

    # ------------------------------------------------------------------ #
    # Score
    # ------------------------------------------------------------------ #
    def _detect_score(self, prev: GameState, state: GameState, events: list, rnd: int) -> None:
        prev_ct, prev_t = prev.ct_score, prev.t_score
        ct, t = state.ct_score, state.t_score
        if ct is None or t is None:
            return
        if ct != prev_ct or t != prev_t:
            events.append(ScoreChanged(round_number=rnd, ct_score=ct, t_score=t))

    # ------------------------------------------------------------------ #
    def _timestamp(self, state: GameState) -> float:
        if state.provider and state.provider.timestamp:
            return float(state.provider.timestamp)
        return time.monotonic()

    def reset(self) -> None:
        """Forget all state (e.g. when a new match/map begins)."""
        self._prev = None
        self._match_started = False
        self._knife_round_done = False
        self._reset_round_state(-1)


def _best_of(state: GameState) -> int:
    """Series format (Bo1/Bo3/Bo5) from GSI's matches-to-win-series, else 0."""
    to_win = state.map.num_matches_to_win_series if state.map else None
    if not to_win or to_win < 1:
        return 0
    return 2 * to_win - 1  # to_win 1 -> Bo1, 2 -> Bo3, 3 -> Bo5


def is_knife_round(state: GameState) -> bool:
    """Heuristic: a live round where every armed player holds only a knife.

    In a knife round players carry nothing but their knife (the bomb aside), so no
    one has a pistol/rifle/SMG. That's a far more reliable signal than round number
    (knife rounds can be warm-up-like), and it can't be confused with an eco, where
    players still keep their spawn pistol.
    """
    source = state.allplayers or {}
    if len(source) < 2:
        return False
    knife_only_players = 0
    for player in source.values():
        weapons = player.weapons or {}
        real = [w for w in weapons.values() if (w.type or "") not in ("C4", "")]
        if not real:
            continue  # no weapon data for this player — ignore, don't veto
        if any((w.type or "") != "Knife" for w in real):
            return False  # someone has a real gun -> not a knife round
        knife_only_players += 1
    return knife_only_players >= 2
