"""Packaged UI assets (the brand logo / window icon).

Kept Qt-free so non-UI code (and tests) can resolve the asset path without
importing PySide6. The file is shipped as package data (see ``pyproject.toml``).
"""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
LOGO_FILE = ASSETS_DIR / "logo.png"


def logo_path() -> Path:
    """Absolute path to the packaged brand logo (PNG, transparent background)."""
    return LOGO_FILE


def has_logo() -> bool:
    return LOGO_FILE.is_file()
