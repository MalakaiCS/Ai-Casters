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


class WebSocketOBSController:
    """Real OBS control over the OBS WebSocket (``obsws-python``)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4455, password: str = "") -> None:
        self._host = host
        self._port = port
        self._password = password
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def connect(self) -> None:
        try:
            import obsws_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - only without the SDK
            raise RuntimeError(
                "OBS integration requires obsws-python. Install OBS extras: "
                'pip install "ai-esports-caster[obs]"'
            ) from exc
        self._client = obsws_python.ReqClient(
            host=self._host, port=self._port, password=self._password
        )
        _log.info("Connected to OBS at %s:%d", self._host, self._port)

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
