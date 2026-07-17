"""Find the CS2 ``csgo/cfg`` folder so the GSI config can be installed in one click.

CS2 delivers Game State Integration to **every** ``gamestate_integration_*.cfg``
in that folder at once, so ours can live alongside a HUD manager's (Lexogrine,
etc.) without conflict — the operator just needs our file dropped in. This module
locates the folder from the Steam install and its library folders; it degrades to
returning ``None`` (the caller then asks the user to pick the folder) if anything
can't be found.
"""

from __future__ import annotations

import re
from pathlib import Path

_CS2_TAIL = Path("steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg")


def _steam_roots() -> list[Path]:
    """Candidate Steam install roots (registry on Windows, then common paths)."""
    roots: list[Path] = []
    try:  # pragma: no cover - Windows only
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for value in ("SteamPath", "InstallPath"):
                        try:
                            path, _ = winreg.QueryValueEx(handle, value)
                            roots.append(Path(str(path)))
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass

    # Common fallbacks (Windows default, plus Linux/macOS for dev).
    roots.extend(
        [
            Path("C:/Program Files (x86)/Steam"),
            Path("C:/Program Files/Steam"),
            Path.home() / ".steam/steam",
            Path.home() / ".local/share/Steam",
            Path.home() / "Library/Application Support/Steam",
        ]
    )
    # De-dupe while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _library_paths(steam_root: Path) -> list[Path]:
    """Every Steam library root (games can live on other drives)."""
    libraries = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return libraries
    # Grab each "path"  "X:\\SteamLibrary" entry regardless of vdf schema version.
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        libraries.append(Path(match.group(1).replace("\\\\", "\\")))
    return libraries


def find_cs2_cfg_dir() -> Path | None:
    """Return the CS2 ``csgo/cfg`` directory, or None if it can't be located."""
    for steam_root in _steam_roots():
        if not steam_root.exists():
            continue
        for library in _library_paths(steam_root):
            candidate = library / _CS2_TAIL
            if candidate.is_dir():
                return candidate
    return None
