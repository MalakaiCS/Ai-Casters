"""Tests for subscription duration presets."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_caster.auth.durations import DEFAULT_DURATION, DURATION_PRESETS, DurationPreset

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_dated_preset_computes_expiry():
    preset = DurationPreset("30 days", 30)
    expiry = preset.expires_at(now=NOW)
    assert expiry == datetime(2026, 1, 31, tzinfo=UTC)


def test_lifetime_preset_has_no_expiry():
    preset = DurationPreset("Lifetime", None)
    assert preset.expires_at(now=NOW) is None


def test_presets_cover_expected_windows():
    labels = [p.label for p in DURATION_PRESETS]
    assert "1 day" in labels
    assert "Lifetime" in labels
    assert DEFAULT_DURATION.days == 30
