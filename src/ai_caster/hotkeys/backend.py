"""Global-hotkey backends.

The backend is the seam to the OS keyboard hook. The default
:class:`NullHotkeyBackend` registers nothing (the actions stay reachable from the
UI), so the app runs on any machine and the hotkey wiring is tested without
touching real input devices. :class:`PynputHotkeyBackend` installs true global
hotkeys via ``pynput`` (the ``[hotkeys]`` extra), lazy-imported.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from ai_caster.core.logging import get_logger

_log = get_logger("hotkeys.backend")


@runtime_checkable
class HotkeyBackend(Protocol):
    """Registers OS-global hotkeys that invoke callbacks."""

    @property
    def name(self) -> str: ...

    def start(self, bindings: dict[str, Callable[[], None]]) -> None: ...

    def stop(self) -> None: ...


class NullHotkeyBackend:
    """Records bindings but installs no OS hook (offline default / test double)."""

    name = "null"

    def __init__(self) -> None:
        self.bindings: dict[str, Callable[[], None]] = {}
        self.running = False

    def start(self, bindings: dict[str, Callable[[], None]]) -> None:
        self.bindings = dict(bindings)
        self.running = True

    def stop(self) -> None:
        self.running = False


class PynputHotkeyBackend:
    """Real global hotkeys via ``pynput`` (optional)."""

    name = "pynput"

    def __init__(self) -> None:
        self._listener = None

    @staticmethod
    def _to_pynput(hotkey: str) -> str:
        """Translate ``"Ctrl+Alt+C"`` to pynput's ``"<ctrl>+<alt>+c"`` form."""
        parts = []
        for token in hotkey.split("+"):
            key = token.strip().lower()
            if key in {"ctrl", "control"}:
                parts.append("<ctrl>")
            elif key == "alt":
                parts.append("<alt>")
            elif key in {"shift"}:
                parts.append("<shift>")
            elif key in {"cmd", "super", "win"}:
                parts.append("<cmd>")
            else:
                parts.append(key)
        return "+".join(parts)

    def start(self, bindings: dict[str, Callable[[], None]]) -> None:
        try:  # pragma: no cover - only exercised with pynput + a display
            from pynput import keyboard  # type: ignore
        except ImportError as exc:  # pragma: no cover - only without pynput
            raise RuntimeError(
                "Global hotkeys require pynput. Install the hotkeys extra: "
                'pip install "ai-esports-caster[hotkeys]"'
            ) from exc
        mapping = {  # pragma: no cover - needs a real input backend
            self._to_pynput(hotkey): callback for hotkey, callback in bindings.items()
        }
        self._listener = keyboard.GlobalHotKeys(mapping)  # pragma: no cover
        self._listener.start()  # pragma: no cover

    def stop(self) -> None:
        if self._listener is not None:  # pragma: no cover - needs a real listener
            self._listener.stop()
            self._listener = None
