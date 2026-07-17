"""Map knowledge for early-round map-control commentary.

GSI gives facts (score, economy, who's alive) but not what's happening on screen,
so the desk otherwise goes quiet during the opening of a round while teams take
map control. This module supplies the *tactical* colour — the key areas of each
map — so the casters can talk about the fight for space at the start of a round
("the battle for Banana", "control of Mid").

Everything here is framed as tendency/expectation ("expect", "watch for", "the
fight for…") — never a claim about what a specific player is doing right now —
so it respects the hard rule against inventing facts while still filling the gap.
"""

from __future__ import annotations

# Key contested areas per map, opening area first. Names are the common callouts.
MAP_AREAS: dict[str, list[str]] = {
    "de_mirage": ["Mid", "A Ramp", "Palace", "B Apartments", "Connector"],
    "de_inferno": ["Banana", "Mid", "Apartments", "Arch", "Short A"],
    "de_dust2": ["Mid", "Long A", "Catwalk", "B Tunnels", "Lower Tunnels"],
    "de_nuke": ["Outside", "Ramp", "Lobby", "Secret", "Heaven"],
    "de_overpass": ["Monster", "Long A", "Connector", "Bathrooms", "B Short"],
    "de_ancient": ["Mid", "A Main", "B Ramp", "Cave", "Donut"],
    "de_anubis": ["Mid", "A Main", "B Palace", "Water", "Canals"],
    "de_vertigo": ["A Ramp", "Mid", "B Stairs", "Connector", "Ladder"],
    "de_train": ["Ivy", "Popdog", "B Halls", "A Main", "Connector"],
    "de_cache": ["Mid", "A Main", "Squeaky", "B Highway", "Vents"],
}

_GENERIC_AREAS = ["mid", "the key chokepoints", "the flanks", "map control"]


def areas_for(map_name: str | None) -> list[str]:
    """The contested areas for a map (case/prefix tolerant), or generic fallbacks."""
    if not map_name:
        return _GENERIC_AREAS
    key = map_name.strip().lower()
    if key in MAP_AREAS:
        return MAP_AREAS[key]
    # Tolerate names without the de_ prefix or with suffixes.
    for name, areas in MAP_AREAS.items():
        if key in name or name.split("_")[-1] in key:
            return areas
    return _GENERIC_AREAS


def area_for(map_name: str | None, rotation: int = 0) -> str:
    """Pick a contested area, rotating so the desk mentions different spots."""
    areas = areas_for(map_name)
    return areas[rotation % len(areas)] if areas else "map control"
