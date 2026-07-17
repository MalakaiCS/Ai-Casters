"""The hotkey manager (Module 1 completion, M9).

Maps configured key combinations to :class:`HotkeyAction` callbacks and drives a
:class:`HotkeyBackend`. :meth:`trigger` invokes an action directly (used by tests
and by any in-app control), so the action wiring is verified without a real
keyboard hook. A callback raising never propagates out of a hotkey press.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_caster.config.models import HotkeySettings
from ai_caster.core.logging import get_logger
from ai_caster.hotkeys.actions import HotkeyAction
from ai_caster.hotkeys.backend import HotkeyBackend, NullHotkeyBackend

_log = get_logger("hotkeys.manager")


class HotkeyManager:
    """Binds hotkey combinations to actions and manages the OS backend."""

    def __init__(
        self,
        settings: HotkeySettings,
        callbacks: dict[HotkeyAction, Callable[[], None]],
        *,
        backend: HotkeyBackend | None = None,
    ) -> None:
        self._settings = settings
        self._callbacks = dict(callbacks)
        self._backend = backend or NullHotkeyBackend()
        self._running = False

    @property
    def backend(self) -> HotkeyBackend:
        return self._backend

    @property
    def is_running(self) -> bool:
        return self._running

    def key_for(self, action: HotkeyAction) -> str:
        """The configured key combination bound to ``action``."""
        return str(getattr(self._settings, action.value, ""))

    def _binding_map(self) -> dict[str, Callable[[], None]]:
        """{key combination -> a guarded callback} for the configured actions."""
        bindings: dict[str, Callable[[], None]] = {}
        for action, callback in self._callbacks.items():
            key = self.key_for(action)
            if key:
                bindings[key] = self._guard(action, callback)
        return bindings

    def _guard(self, action: HotkeyAction, callback: Callable[[], None]) -> Callable[[], None]:
        def _run() -> None:
            try:
                callback()
            except Exception:  # noqa: BLE001 - a hotkey must never crash the app
                _log.exception("Hotkey action %s failed", action.value)

        return _run

    def trigger(self, action: HotkeyAction) -> None:
        """Invoke an action's callback directly (UI buttons / tests)."""
        callback = self._callbacks.get(action)
        if callback is None:
            return
        self._guard(action, callback)()

    def start(self) -> None:
        if self._running:
            return
        try:
            self._backend.start(self._binding_map())
            self._running = True
            _log.info("Hotkeys registered via %s backend", self._backend.name)
        except Exception:  # noqa: BLE001 - missing backend must not block startup
            _log.exception("Could not register global hotkeys; UI controls still work.")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            self._backend.stop()
        finally:
            self._running = False

    def dispose(self) -> None:
        self.stop()
