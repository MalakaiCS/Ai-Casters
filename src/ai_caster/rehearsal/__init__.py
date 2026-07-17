"""Rehearsal mode — record a live GSI feed and replay it for testing/tuning.

Recording taps the authenticated live payloads passing through the GSI receiver
and writes them to a timestamped ``.jsonl`` clip (with the auth token stripped).
Playback feeds a saved clip back through the receiver's replay path at a chosen
speed, so the *entire* commentary stack — match model, director, banter, voices —
runs exactly as it would live, on any machine, with no CS2 running. That makes
the whole cast testable and lets an operator tune voices, timing and tone against
a real match before going live.
"""

from ai_caster.rehearsal.player import (
    RehearsalClip,
    RehearsalFrame,
    RehearsalPlayer,
    load_clip,
    schedule,
)
from ai_caster.rehearsal.recorder import GsiRecorder

__all__ = [
    "GsiRecorder",
    "RehearsalClip",
    "RehearsalFrame",
    "RehearsalPlayer",
    "load_clip",
    "schedule",
]
