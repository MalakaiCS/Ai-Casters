"""Build an OBS controller from settings.

Centralises the choice so both the composition root and the UI (when the operator
enables/reconfigures OBS at runtime) construct the controller the same way.
"""

from __future__ import annotations

from ai_caster.config.models import OBSSettings
from ai_caster.obs.controller import (
    NullOBSController,
    OBSController,
    WebSocketOBSController,
)


def obs_sdk_available() -> bool:
    """Whether the obsws-python SDK is importable in this build."""
    return WebSocketOBSController.sdk_available()


def create_obs_controller(settings: OBSSettings) -> OBSController:
    """A WebSocket controller when OBS integration is enabled, else the no-op.

    Construction never opens a socket — that happens in :meth:`connect` — so an
    unreachable OBS only fails when the operator actually connects.
    """
    if settings.enabled and obs_sdk_available():
        return WebSocketOBSController(
            host=settings.host,
            port=settings.port,
            password=settings.password,
        )
    return NullOBSController()
