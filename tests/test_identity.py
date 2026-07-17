"""Tests for the stable per-install device identity."""

from __future__ import annotations

from pathlib import Path

from ai_caster.core.identity import get_or_create_device_id


def test_device_id_is_created_and_stable(tmp_path: Path):
    first = get_or_create_device_id(tmp_path)
    assert first
    # A second call returns the same persisted id.
    assert get_or_create_device_id(tmp_path) == first
    assert (tmp_path / "device.json").exists()


def test_corrupt_device_file_is_regenerated(tmp_path: Path):
    (tmp_path / "device.json").write_text("not json", encoding="utf-8")
    device_id = get_or_create_device_id(tmp_path)
    assert device_id
    # And it is now stable.
    assert get_or_create_device_id(tmp_path) == device_id
