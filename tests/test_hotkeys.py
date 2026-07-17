"""Tests for the hotkey manager and its backends."""

from __future__ import annotations

from ai_caster.config.models import HotkeySettings
from ai_caster.hotkeys.actions import HotkeyAction
from ai_caster.hotkeys.backend import NullHotkeyBackend, PynputHotkeyBackend
from ai_caster.hotkeys.manager import HotkeyManager


def _counter():
    calls = {"n": 0}

    def _inc() -> None:
        calls["n"] += 1

    return calls, _inc


def test_key_for_reads_settings():
    settings = HotkeySettings(toggle_casting="Ctrl+Alt+X")
    manager = HotkeyManager(settings, {})
    assert manager.key_for(HotkeyAction.TOGGLE_CASTING) == "Ctrl+Alt+X"


def test_trigger_invokes_callback():
    calls, inc = _counter()
    manager = HotkeyManager(HotkeySettings(), {HotkeyAction.MUTE_ALL: inc})
    manager.trigger(HotkeyAction.MUTE_ALL)
    assert calls["n"] == 1


def test_trigger_unbound_action_is_noop():
    manager = HotkeyManager(HotkeySettings(), {})
    manager.trigger(HotkeyAction.FORCE_REPLAY_MODE)  # no callback registered


def test_callback_exception_is_swallowed():
    def _boom() -> None:
        raise RuntimeError("nope")

    manager = HotkeyManager(HotkeySettings(), {HotkeyAction.TOGGLE_CASTING: _boom})
    manager.trigger(HotkeyAction.TOGGLE_CASTING)  # must not raise


def test_start_registers_binding_map_with_backend():
    calls, inc = _counter()
    backend = NullHotkeyBackend()
    settings = HotkeySettings(toggle_casting="Ctrl+Alt+C", mute_all="Ctrl+Alt+M")
    manager = HotkeyManager(
        settings,
        {HotkeyAction.TOGGLE_CASTING: inc, HotkeyAction.MUTE_ALL: inc},
        backend=backend,
    )
    manager.start()
    assert manager.is_running and backend.running
    assert set(backend.bindings) == {"Ctrl+Alt+C", "Ctrl+Alt+M"}
    # The registered bindings dispatch to the callbacks.
    backend.bindings["Ctrl+Alt+C"]()
    assert calls["n"] == 1


def test_stop_and_dispose():
    backend = NullHotkeyBackend()
    manager = HotkeyManager(HotkeySettings(), {}, backend=backend)
    manager.start()
    manager.dispose()
    assert not manager.is_running and not backend.running


def test_pynput_hotkey_translation():
    assert PynputHotkeyBackend._to_pynput("Ctrl+Alt+C") == "<ctrl>+<alt>+c"
    assert PynputHotkeyBackend._to_pynput("Shift+R") == "<shift>+r"
