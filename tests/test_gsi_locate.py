"""Tests for locating the CS2 cfg folder and the default-output sink factory."""

from __future__ import annotations

import ai_caster.gsi.locate as locate
import ai_caster.voice.factory as factory
from ai_caster.gsi.locate import _CS2_TAIL, _library_paths, find_cs2_cfg_dir
from ai_caster.voice.sink import NullSink


def test_library_paths_parses_vdf(tmp_path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n  "0" { "path" "D:\\\\Games\\\\SteamLibrary" }\n}\n',
        encoding="utf-8",
    )
    paths = _library_paths(steam)
    assert steam in paths
    assert any("SteamLibrary" in str(p) for p in paths)


def test_find_cs2_cfg_dir_found(tmp_path, monkeypatch):
    steam = tmp_path / "Steam"
    cfg = steam / _CS2_TAIL
    cfg.mkdir(parents=True)
    monkeypatch.setattr(locate, "_steam_roots", lambda: [steam])
    assert find_cs2_cfg_dir() == cfg


def test_find_cs2_cfg_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(locate, "_steam_roots", lambda: [tmp_path / "nope"])
    assert find_cs2_cfg_dir() is None


def test_default_output_sink_falls_back_to_null_without_sounddevice(monkeypatch):
    monkeypatch.setattr(factory, "_available", lambda mod: False)
    sink = factory.create_default_output_sink(24000, "monitor")
    assert isinstance(sink, NullSink)
    assert factory.sound_output_available() is False


def test_default_device_string_routes_to_default_output(monkeypatch):
    # With sounddevice "available", device="default" builds a device sink (blank
    # device = OS default), not a Null sink.
    monkeypatch.setattr(factory, "_available", lambda mod: True)
    sink = factory.create_output_sink("default", 24000, "play_by_play")
    assert type(sink).__name__ == "SoundDeviceSink"
