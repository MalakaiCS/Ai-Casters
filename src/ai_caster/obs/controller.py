"""OBS controller interface and implementations.

:class:`NullOBSController` records requested actions and is the offline default
(and the test double). :class:`WebSocketOBSController` drives a real OBS instance
via ``obsws-python`` (the ``[obs]`` extra), lazy-imported so the package doesn't
require it unless OBS integration is actually used.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_caster.core.logging import get_logger

_log = get_logger("obs.controller")


@runtime_checkable
class OBSController(Protocol):
    """Controls an OBS instance."""

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def set_scene(self, scene: str) -> None: ...

    def get_current_scene(self) -> str | None: ...

    def list_scenes(self) -> list[str]: ...


class NullOBSController:
    """No-op controller that records actions (offline default / test double)."""

    def __init__(self) -> None:
        self._connected = False
        self.scenes_set: list[str] = []
        self.current_scene: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_scene(self, scene: str) -> None:
        self.scenes_set.append(scene)
        self.current_scene = scene

    def get_current_scene(self) -> str | None:
        return self.current_scene

    def list_scenes(self) -> list[str]:
        return []


class WebSocketOBSController:
    """Real OBS control over the OBS WebSocket (``obsws-python``)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4455, password: str = "") -> None:
        self._host = host
        self._port = port
        self._password = password
        self._client = None
        self.current_scene: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @staticmethod
    def sdk_available() -> bool:
        import importlib.util

        return importlib.util.find_spec("obsws_python") is not None

    def connect(self) -> None:
        try:
            import obsws_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - only without the SDK
            raise RuntimeError(
                "OBS integration requires the obsws-python package, which isn't "
                "available in this build."
            ) from exc
        # ReqClient connects and does the identify handshake on construction, so a
        # bad port/password or a closed OBS raises right here — which is exactly
        # what the UI wants to surface.
        self._client = obsws_python.ReqClient(
            host=self._host, port=self._port, password=self._password, timeout=5
        )
        # Prime the current scene so the UI has something to show immediately and
        # so a successful handshake is confirmed by a real request.
        self.current_scene = self.get_current_scene()
        _log.info(
            "Connected to OBS at %s:%d (scene=%s)", self._host, self._port, self.current_scene
        )

    def disconnect(self) -> None:
        if self._client is not None:
            try:  # pragma: no cover - depends on live OBS
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def set_scene(self, scene: str) -> None:
        if self._client is None:
            return
        self._client.set_current_program_scene(scene)  # pragma: no cover - live OBS
        self.current_scene = scene

    def get_current_scene(self) -> str | None:
        if self._client is None:
            return None
        try:  # pragma: no cover - live OBS
            response = self._client.get_current_program_scene()
        except Exception:  # noqa: BLE001 - never let an OBS hiccup crash the caller
            _log.exception("Failed to read the current OBS scene")
            return self.current_scene
        scene = _scene_name(response)
        if scene:
            self.current_scene = scene
        return scene

    def list_scenes(self) -> list[str]:
        if self._client is None:
            return []
        try:  # pragma: no cover - live OBS
            response = self._client.get_scene_list()
        except Exception:  # noqa: BLE001
            _log.exception("Failed to list OBS scenes")
            return []
        return _scene_names(getattr(response, "scenes", None))


def _scene_name(response: object) -> str | None:
    """Read the current scene name across obsws-python / OBS version differences."""
    for attr in ("current_program_scene_name", "scene_name", "currentProgramSceneName"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _scene_names(scenes: object) -> list[str]:
    """Extract scene names from a get_scene_list response's ``scenes`` field.

    OBS returns newest-first; each entry is a dict with a ``sceneName`` key (or an
    object with that attribute across library versions).
    """
    if not isinstance(scenes, list):
        return []
    names: list[str] = []
    for entry in scenes:
        name = None
        if isinstance(entry, dict):
            name = entry.get("sceneName") or entry.get("scene_name") or entry.get("name")
        else:
            name = getattr(entry, "sceneName", None) or getattr(entry, "scene_name", None)
        if isinstance(name, str) and name:
            names.append(name)
    names.reverse()  # present top-to-bottom as OBS shows them
    return names
