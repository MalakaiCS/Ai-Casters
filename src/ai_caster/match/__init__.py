"""Match state — the single source of truth for the live match.

Milestone 1 provides a thread-safe store over GSI only. The full Match State
Engine (M2) will fuse Server events > GSI > Vision > Inference on top of this.
"""

from ai_caster.match.state import MatchSnapshot, MatchStateStore

__all__ = ["MatchSnapshot", "MatchStateStore"]
