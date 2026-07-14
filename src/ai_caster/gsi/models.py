"""Typed models for the CS2 Game State Integration payload.

CS2 posts a JSON document whose shape depends on the *components* enabled in the
game config and on whether the client is a player or a spectator/observer. Fields
are therefore almost all optional. We use ``extra="allow"`` so forward-compatible
or component-specific keys are preserved rather than dropped — important because
the game occasionally adds fields.

Only the subset relevant to casting is given first-class typed fields; anything
else is still accessible via the retained extras. The Match State Engine (M2)
consumes these models; it is *not* the job of this module to fuse or interpret
them, only to parse faithfully.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _GSIModel(BaseModel):
    """Base: tolerate and retain unknown keys from the game."""

    model_config = ConfigDict(extra="allow")


class Provider(_GSIModel):
    """Identifies the game client that produced the payload."""

    name: str | None = None
    appid: int | None = None
    version: int | None = None
    steamid: str | None = None
    timestamp: int | None = None


class TeamState(_GSIModel):
    """Per-team block found under ``map.team_ct`` / ``map.team_t``."""

    score: int | None = None
    name: str | None = None
    consecutive_round_losses: int | None = None
    timeouts_remaining: int | None = None
    matches_won_this_series: int | None = None


class MapState(_GSIModel):
    """The ``map`` component: match-level context."""

    name: str | None = None
    mode: str | None = None
    phase: str | None = Field(default=None, description="warmup/live/intermission/gameover")
    round: int | None = Field(default=None, description="Zero-based round index.")
    team_ct: TeamState | None = None
    team_t: TeamState | None = None
    num_matches_to_win_series: int | None = None
    current_spectators: int | None = None
    souvenirs_total: int | None = None


class RoundState(_GSIModel):
    """The ``round`` component: current round status."""

    phase: str | None = Field(default=None, description="freezetime/live/over")
    bomb: str | None = Field(default=None, description="planted/exploded/defused (if present)")
    win_team: str | None = None


class PlayerState(_GSIModel):
    """Health/armour/flash/economy block under ``player.state``."""

    health: int | None = None
    armor: int | None = None
    helmet: bool | None = None
    flashed: int | None = None
    smoked: int | None = None
    burning: int | None = None
    money: int | None = None
    round_kills: int | None = None
    round_killhs: int | None = None
    round_totaldmg: int | None = None
    equip_value: int | None = None
    defusekit: bool | None = None


class PlayerMatchStats(_GSIModel):
    """Cumulative match stats under ``player.match_stats``."""

    kills: int | None = None
    assists: int | None = None
    deaths: int | None = None
    mvps: int | None = None
    score: int | None = None


class Weapon(_GSIModel):
    """A single weapon entry within ``player.weapons``."""

    name: str | None = None
    paintkit: str | None = None
    type: str | None = None
    state: str | None = Field(default=None, description="active/holstered/reloading")
    ammo_clip: int | None = None
    ammo_clip_max: int | None = None
    ammo_reserve: int | None = None


class Player(_GSIModel):
    """The ``player`` component: the currently observed player (spectator feed)
    or the local player."""

    steamid: str | None = None
    name: str | None = None
    observer_slot: int | None = None
    team: str | None = None
    activity: str | None = Field(default=None, description="playing/menu/textinput")
    state: PlayerState | None = None
    match_stats: PlayerMatchStats | None = None
    weapons: dict[str, Weapon] | None = None
    position: str | None = None
    forward: str | None = None
    spectarget: str | None = None


class Auth(_GSIModel):
    """The ``auth`` block echoing the shared token from the game config."""

    token: str | None = None


class GameState(_GSIModel):
    """A complete, parsed GSI payload.

    ``previously`` and ``added`` are raw dicts: CS2 mirrors the top-level shape
    inside them to indicate what changed, which is useful for event detection
    (M2) but not worth re-typing.
    """

    provider: Provider | None = None
    map: MapState | None = None
    round: RoundState | None = None
    player: Player | None = None
    allplayers: dict[str, Player] | None = None
    phase_countdowns: dict[str, object] | None = None
    previously: dict[str, object] | None = None
    added: dict[str, object] | None = None
    auth: Auth | None = None

    # -- convenience accessors used by the UI / diagnostics -------------- #
    @property
    def map_name(self) -> str | None:
        return self.map.name if self.map else None

    @property
    def round_number(self) -> int | None:
        return self.map.round if self.map else None

    @property
    def ct_score(self) -> int | None:
        return self.map.team_ct.score if self.map and self.map.team_ct else None

    @property
    def t_score(self) -> int | None:
        return self.map.team_t.score if self.map and self.map.team_t else None

    @property
    def observed_player_name(self) -> str | None:
        return self.player.name if self.player else None
