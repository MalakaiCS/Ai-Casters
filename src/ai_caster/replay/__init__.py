"""Module 15 — Replay Integration.

The replay system runs *externally*; this module receives its events (started,
ended, type, speed) over a small HTTP endpoint, maintains an authoritative replay
state, and publishes changes on the bus. The Commentary Director consumes this to
enforce the hard rule: **never describe replay footage as live.**
"""

from ai_caster.replay.models import ReplayState, ReplayType
from ai_caster.replay.receiver import ReplayReceiver
from ai_caster.replay.server import ReplayServer

__all__ = ["ReplayState", "ReplayType", "ReplayReceiver", "ReplayServer"]
