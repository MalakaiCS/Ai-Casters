"""Module 2 — Settings Manager.

Typed, validated, persisted application configuration.
"""

from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import AppSettings

__all__ = ["SettingsManager", "AppSettings"]
