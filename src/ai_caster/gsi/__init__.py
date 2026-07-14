"""Module 5 — CS2 Game State Integration (GSI) receiver.

Ingests, authenticates and parses the JSON payloads CS2 posts over HTTP, exposes
them as typed models, and publishes updates on the event bus.
"""

from ai_caster.gsi.models import GameState
from ai_caster.gsi.receiver import GSIReceiver
from ai_caster.gsi.server import GSIServer

__all__ = ["GameState", "GSIReceiver", "GSIServer"]
