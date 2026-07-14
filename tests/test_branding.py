"""The packaged brand logo must ship and be resolvable (Qt-free check)."""

from __future__ import annotations

from ai_caster import __brand__, __tagline__
from ai_caster.ui.assets import has_logo, logo_path


def test_logo_is_packaged():
    assert has_logo(), "brand logo asset is missing from the package"
    path = logo_path()
    assert path.suffix == ".png"
    # A real image, not an empty placeholder.
    assert path.stat().st_size > 1000


def test_logo_is_a_png():
    with logo_path().open("rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"


def test_brand_constants():
    assert __brand__ == "AI Casters"
    assert "Commentary" in __tagline__
