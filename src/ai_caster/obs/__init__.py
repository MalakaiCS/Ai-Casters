"""Module 16 — OBS Integration.

Connects to OBS via its WebSocket, switches scenes, and reacts to replay state
(switching to a replay scene while a replay is active and back to live when it
ends). The controller sits behind an interface with an offline no-op default, so
the integration runs and is tested without OBS; the real WebSocket client loads
behind the ``[obs]`` extra.
"""

from ai_caster.obs.controller import NullOBSController, OBSController
from ai_caster.obs.integration import OBSIntegration

__all__ = ["OBSController", "NullOBSController", "OBSIntegration"]
