"""The rich live match model — the display/analysis view of the match.

Where :mod:`ai_caster.match.state` holds a lightweight latest-snapshot for the
UI headline, this module builds the **complete live match model** the
specification calls for: round, score, series score, economy, per-player
health/armour/weapons/ammo, bomb, players alive, observed player, map, match
phase, plus derived **momentum**, **round importance** and **series importance**.

The model is rebuilt from each GSI payload rather than mutated in place, so the
network thread never hands a half-updated object to a reader. Round *history* is
carried forward by the :class:`~ai_caster.match.engine.MatchStateEngine`.

Everything here is derived from GSI only in Milestone 1/2; the fields are shaped
so Vision (M4) can later enrich them without changing consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from ai_caster.gsi.models import GameState

# CS2 standard MR12: first team to this many round wins takes the map.
DEFAULT_ROUNDS_TO_WIN = 13
# Number of recent rounds that feed the momentum calculation.
MOMENTUM_WINDOW = 5


class Side(StrEnum):
    CT = "CT"
    T = "T"

    @property
    def other(self) -> Side:
        return Side.T if self is Side.CT else Side.CT


class BuyType(StrEnum):
    """Coarse economy classification of a team's round investment."""

    UNKNOWN = "unknown"
    ECO = "eco"
    FORCE = "force"
    FULL = "full"


class RoundEndReason(StrEnum):
    ELIMINATION = "elimination"
    BOMB_EXPLODED = "bomb_exploded"
    BOMB_DEFUSED = "bomb_defused"
    TIME_EXPIRED = "time_expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlayerModel:
    """Normalised per-player state for the current tick."""

    steamid: str
    name: str
    side: Side | None
    health: int = 0
    armor: int = 0
    helmet: bool = False
    money: int = 0
    equip_value: int = 0
    round_kills: int = 0
    round_headshots: int = 0
    round_damage: int = 0
    match_kills: int = 0
    match_deaths: int = 0
    match_assists: int = 0
    match_mvps: int = 0
    match_score: int = 0
    active_weapon: str | None = None
    active_ammo_clip: int | None = None
    active_ammo_reserve: int | None = None

    @property
    def is_alive(self) -> bool:
        return self.health > 0


@dataclass(frozen=True)
class TeamModel:
    """Aggregated per-team state."""

    side: Side
    name: str
    score: int = 0
    money: int = 0
    equip_value: int = 0
    players_alive: int = 0
    players_total: int = 0
    consecutive_round_losses: int = 0
    buy_type: BuyType = BuyType.UNKNOWN


@dataclass(frozen=True)
class SeriesState:
    """Best-of-N series context, taken from GSI when the tournament server
    provides it."""

    ct_maps_won: int = 0
    t_maps_won: int = 0
    maps_to_win: int = 0

    @property
    def is_map_point(self) -> bool:
        """Whether either team can clinch the series by winning the current map."""
        if self.maps_to_win <= 0:
            return False
        return self.ct_maps_won == self.maps_to_win - 1 or self.t_maps_won == self.maps_to_win - 1


@dataclass(frozen=True)
class Momentum:
    """Directional momentum in ``[-1, 1]``: positive favours CT, negative T."""

    value: float = 0.0

    @property
    def leader(self) -> Side | None:
        if self.value > 0.15:
            return Side.CT
        if self.value < -0.15:
            return Side.T
        return None

    @property
    def magnitude(self) -> float:
        return abs(self.value)


@dataclass(frozen=True)
class RoundRecord:
    """A finalised historical round."""

    number: int
    winner: Side | None = None
    reason: RoundEndReason = RoundEndReason.UNKNOWN
    bomb_planted: bool = False
    ct_buy: BuyType = BuyType.UNKNOWN
    t_buy: BuyType = BuyType.UNKNOWN


@dataclass(frozen=True)
class LiveMatch:
    """The complete, immutable live match model for one tick."""

    map_name: str | None = None
    match_phase: str | None = None
    round_number: int = 0
    round_phase: str | None = None
    bomb_state: str | None = None
    observed_steamid: str | None = None
    rounds_to_win: int = DEFAULT_ROUNDS_TO_WIN

    ct: TeamModel = field(default_factory=lambda: TeamModel(Side.CT, "CT"))
    t: TeamModel = field(default_factory=lambda: TeamModel(Side.T, "T"))
    series: SeriesState = field(default_factory=SeriesState)
    players: tuple[PlayerModel, ...] = ()
    history: tuple[RoundRecord, ...] = ()
    momentum: Momentum = field(default_factory=Momentum)
    round_importance: float = 0.0
    series_importance: float = 0.0

    # Optional vision annotation (a VisionState). GSI-authoritative gameplay
    # fields above are never derived from this — vision only *annotates* the
    # model (scene/effect cues), honouring Server > GSI > Vision > Inference.
    # Typed loosely to keep the match module independent of the vision package.
    visual: Any = None

    # -- convenience ---------------------------------------------------- #
    @property
    def observed_player(self) -> PlayerModel | None:
        if not self.observed_steamid:
            return None
        return next((p for p in self.players if p.steamid == self.observed_steamid), None)

    def team(self, side: Side) -> TeamModel:
        return self.ct if side is Side.CT else self.t

    def players_on(self, side: Side) -> tuple[PlayerModel, ...]:
        return tuple(p for p in self.players if p.side is side)

    def alive_on(self, side: Side) -> int:
        return sum(1 for p in self.players if p.side is side and p.is_alive)

    @property
    def is_match_point(self) -> bool:
        target = self.rounds_to_win
        return self.ct.score == target - 1 or self.t.score == target - 1

    def with_history(self, history: tuple[RoundRecord, ...]) -> LiveMatch:
        return replace(self, history=history)


# --------------------------------------------------------------------------- #
# Economy classification
# --------------------------------------------------------------------------- #
def classify_buy(equip_value: int, players_total: int) -> BuyType:
    """Classify a team's buy from its total equipment value.

    Thresholds are per-player averages tuned to CS2 pricing: an eco is minimal
    equipment, a force is partial (pistols/SMGs, light armour), a full buy is
    rifles + armour + utility.
    """
    if players_total <= 0:
        return BuyType.UNKNOWN
    avg = equip_value / players_total
    if avg < 1500:
        return BuyType.ECO
    if avg < 3500:
        return BuyType.FORCE
    return BuyType.FULL


# --------------------------------------------------------------------------- #
# Building the model from a GSI payload
# --------------------------------------------------------------------------- #
def _side_from_str(value: str | None) -> Side | None:
    if value == "CT":
        return Side.CT
    if value == "T":
        return Side.T
    return None


def _active_weapon(weapons: dict | None) -> tuple[str | None, int | None, int | None]:
    if not weapons:
        return None, None, None
    for weapon in weapons.values():
        if weapon.state == "active":
            return weapon.name, weapon.ammo_clip, weapon.ammo_reserve
    return None, None, None


def build_players(state: GameState) -> tuple[PlayerModel, ...]:
    """Build the player list from the ``allplayers`` block (spectator feed).

    Falls back to the single ``player`` block when spectating is unavailable.
    """
    players: list[PlayerModel] = []
    source = state.allplayers or (
        {} if state.player is None else {state.player.steamid or "": state.player}
    )
    for steamid, player in source.items():
        st = player.state
        weapon_name, clip, reserve = _active_weapon(player.weapons)
        ms = player.match_stats
        players.append(
            PlayerModel(
                steamid=steamid or (player.steamid or ""),
                name=player.name or "unknown",
                side=_side_from_str(player.team),
                health=(st.health if st and st.health is not None else 0),
                armor=(st.armor if st and st.armor is not None else 0),
                helmet=bool(st.helmet) if st else False,
                money=(st.money if st and st.money is not None else 0),
                equip_value=(st.equip_value if st and st.equip_value is not None else 0),
                round_kills=(st.round_kills if st and st.round_kills is not None else 0),
                round_headshots=(st.round_killhs if st and st.round_killhs is not None else 0),
                round_damage=(st.round_totaldmg if st and st.round_totaldmg is not None else 0),
                match_kills=(ms.kills if ms and ms.kills is not None else 0),
                match_deaths=(ms.deaths if ms and ms.deaths is not None else 0),
                match_assists=(ms.assists if ms and ms.assists is not None else 0),
                match_mvps=(ms.mvps if ms and ms.mvps is not None else 0),
                match_score=(ms.score if ms and ms.score is not None else 0),
                active_weapon=weapon_name,
                active_ammo_clip=clip,
                active_ammo_reserve=reserve,
            )
        )
    return tuple(players)


def _build_team(state: GameState, side: Side, players: tuple[PlayerModel, ...]) -> TeamModel:
    team_block = None
    if state.map:
        team_block = state.map.team_ct if side is Side.CT else state.map.team_t
    side_players = tuple(p for p in players if p.side is side)
    equip = sum(p.equip_value for p in side_players)
    return TeamModel(
        side=side,
        name=(team_block.name if team_block and team_block.name else side.value),
        score=(team_block.score if team_block and team_block.score is not None else 0),
        money=sum(p.money for p in side_players),
        equip_value=equip,
        players_alive=sum(1 for p in side_players if p.is_alive),
        players_total=len(side_players),
        consecutive_round_losses=(
            team_block.consecutive_round_losses
            if team_block and team_block.consecutive_round_losses is not None
            else 0
        ),
        buy_type=classify_buy(equip, len(side_players)),
    )


def _build_series(state: GameState) -> SeriesState:
    ct = state.map.team_ct if state.map else None
    t = state.map.team_t if state.map else None
    maps_to_win = state.map.num_matches_to_win_series if state.map else None
    return SeriesState(
        ct_maps_won=(ct.matches_won_this_series if ct and ct.matches_won_this_series else 0),
        t_maps_won=(t.matches_won_this_series if t and t.matches_won_this_series else 0),
        maps_to_win=(maps_to_win or 0),
    )


def compute_momentum(history: tuple[RoundRecord, ...], window: int = MOMENTUM_WINDOW) -> Momentum:
    """Momentum from recent round winners, weighted toward the most recent round.

    Returns a value in ``[-1, 1]`` (positive = CT). Recent rounds count more, so
    a fresh comeback swings momentum faster than an old lead.
    """
    recent = [r for r in history if r.winner is not None][-window:]
    if not recent:
        return Momentum(0.0)
    total_weight = 0.0
    score = 0.0
    for index, record in enumerate(recent, start=1):
        weight = float(index)  # most recent (last) gets the highest weight
        total_weight += weight
        score += weight * (1.0 if record.winner is Side.CT else -1.0)
    return Momentum(round(score / total_weight, 4) if total_weight else 0.0)


def compute_round_importance(
    ct: TeamModel, t: TeamModel, series: SeriesState, rounds_to_win: int
) -> float:
    """Estimate how pivotal the current round is, in ``[0, 1]``.

    Higher when a team is on match point, when the score is close/late, and when
    the series itself is on the line.
    """
    importance = 0.0
    highest = max(ct.score, t.score)
    # Proximity to winning the map.
    importance += min(highest / max(rounds_to_win, 1), 1.0) * 0.4
    # Match point is a big spike.
    if ct.score == rounds_to_win - 1 or t.score == rounds_to_win - 1:
        importance += 0.35
    # Closeness of the map score.
    diff = abs(ct.score - t.score)
    importance += max(0.0, 0.15 * (1.0 - diff / max(rounds_to_win, 1)))
    # Series stakes.
    if series.is_map_point:
        importance += 0.1
    return round(min(importance, 1.0), 4)


def compute_series_importance(series: SeriesState) -> float:
    """Estimate series stakes of the current map, in ``[0, 1]``."""
    if series.maps_to_win <= 0:
        return 0.0
    lead = max(series.ct_maps_won, series.t_maps_won)
    base = min(lead / series.maps_to_win, 1.0) * 0.6
    if series.is_map_point:
        base += 0.4
    return round(min(base, 1.0), 4)


def build_live_match(
    state: GameState,
    *,
    history: tuple[RoundRecord, ...] = (),
    rounds_to_win: int = DEFAULT_ROUNDS_TO_WIN,
    vision: Any = None,
) -> LiveMatch:
    """Assemble the complete :class:`LiveMatch` from a parsed GSI payload.

    ``vision`` is an optional annotation (a ``VisionState``) attached as-is; it
    never influences the GSI-authoritative fields.
    """
    players = build_players(state)
    ct = _build_team(state, Side.CT, players)
    t = _build_team(state, Side.T, players)
    series = _build_series(state)
    momentum = compute_momentum(history)
    return LiveMatch(
        map_name=state.map_name,
        match_phase=state.map.phase if state.map else None,
        round_number=state.round_number or 0,
        round_phase=state.round.phase if state.round else None,
        bomb_state=state.round.bomb if state.round else None,
        observed_steamid=(state.player.steamid if state.player else None),
        rounds_to_win=rounds_to_win,
        ct=ct,
        t=t,
        series=series,
        players=players,
        history=history,
        momentum=momentum,
        round_importance=compute_round_importance(ct, t, series, rounds_to_win),
        series_importance=compute_series_importance(series),
        visual=vision,
    )
