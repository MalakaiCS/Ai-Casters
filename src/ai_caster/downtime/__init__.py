"""Downtime commentary — desk chatter during timeouts, pauses and breaks."""

from ai_caster.downtime.commentator import DowntimeCommentator
from ai_caster.downtime.detect import LullState, detect_lull

__all__ = ["DowntimeCommentator", "LullState", "detect_lull"]
