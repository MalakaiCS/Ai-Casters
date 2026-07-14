"""Typed configuration models (pydantic v2).

Each settings *area* from the specification is modelled as its own nested group
so the UI can render one section per group and future modules can validate the
slice they care about. Every field has a sensible default so a brand-new install
is fully functional without any user input.

These models describe *configuration only*. They never hold runtime state.
"""

from __future__ import annotations

import secrets
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class _Section(BaseModel):
    """Base for all settings sections.

    ``extra="forbid"`` catches typos in persisted files instead of silently
    dropping them; ``validate_assignment`` keeps live edits valid.
    """

    model_config = {"extra": "forbid", "validate_assignment": True}


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class AIProvider(StrEnum):
    """Selectable backend for the commentary generators (wired up in M6)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    MOCK = "mock"


class Language(StrEnum):
    ENGLISH = "en"
    SPANISH = "es"
    PORTUGUESE = "pt"
    GERMAN = "de"
    FRENCH = "fr"


class CaptureSourceType(StrEnum):
    """Where the observer feed pixels come from (Module 6)."""

    SYNTHETIC = "synthetic"  # generated frames — always available, used for dev/CI
    MONITOR = "monitor"  # a whole monitor / screen region (via mss)
    WINDOW = "window"  # a specific window by title
    CAPTURE_CARD = "capture_card"  # an external capture device (via OpenCV)


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
class GSISettings(_Section):
    """CS2 Game State Integration receiver settings (Module 5)."""

    host: str = Field(default="127.0.0.1", description="Interface the GSI HTTP server binds to.")
    port: int = Field(default=3111, ge=1, le=65535, description="Port CS2 posts GSI data to.")
    auth_token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(24),
        description="Shared secret CS2 must echo back in every payload's auth block.",
    )
    require_auth: bool = Field(
        default=True, description="Reject payloads whose auth token does not match."
    )
    stale_after_seconds: float = Field(
        default=5.0, gt=0, description="Mark the feed disconnected after this much silence."
    )


class VoiceChannelSettings(_Section):
    """Per-channel voice settings. Each voice is fully independent (M7)."""

    enabled: bool = True
    output_device: str = Field(
        default="", description="Windows audio output device name (blank = system default)."
    )
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    muted: bool = False
    latency_ms: int = Field(default=120, ge=0, le=2000)


class VoiceSettings(_Section):
    """Two independent voice channels plus a combined monitor mix (M7)."""

    play_by_play: VoiceChannelSettings = Field(default_factory=VoiceChannelSettings)
    analyst: VoiceChannelSettings = Field(default_factory=VoiceChannelSettings)
    monitor_device: str = Field(
        default="", description="Device for the combined monitor mix (e.g. headphones)."
    )
    monitor_volume: float = Field(default=0.8, ge=0.0, le=1.0)


class OBSSettings(_Section):
    """OBS WebSocket integration (M7)."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=4455, ge=1, le=65535)
    password: str = ""


class ReplaySettings(_Section):
    """External replay-system integration (M5).

    The replay system runs externally; we only receive events on this port and
    must never describe replay footage as live.
    """

    enabled: bool = True
    listen_port: int = Field(default=3112, ge=1, le=65535)
    treat_unknown_as_live: bool = Field(
        default=False,
        description="Safety: if replay state is unknown, assume NOT live unless enabled.",
    )


class CaptureSettings(_Section):
    """Video capture settings (Module 6).

    Defaults to a synthetic source so the application runs on any machine
    (including headless CI). Switch ``source`` to monitor/window/capture_card and
    set the matching locator to capture a real CS2 observer feed.
    """

    source: CaptureSourceType = CaptureSourceType.SYNTHETIC
    target_fps: int = Field(default=60, ge=1, le=240, description="Capture loop target rate.")
    width: int = Field(default=1920, ge=16, le=7680, description="Target/synthetic frame width.")
    height: int = Field(default=1080, ge=16, le=4320, description="Target/synthetic frame height.")
    buffer_size: int = Field(
        default=8, ge=1, le=240, description="Ring-buffer depth for frame look-back."
    )
    use_gpu: bool = Field(
        default=True, description="Upload frames to the GPU when an uploader is available."
    )

    # Source locators (only the one matching ``source`` is used).
    monitor_index: int = Field(default=1, ge=0, description="mss monitor index (0 = virtual all).")
    window_title: str = Field(
        default="Counter-Strike", description="Substring of the window title."
    )
    device_index: int = Field(default=0, ge=0, description="OpenCV capture-card device index.")
    # Optional sub-region (0 width/height = full source).
    region_left: int = Field(default=0, ge=0)
    region_top: int = Field(default=0, ge=0)
    region_width: int = Field(default=0, ge=0)
    region_height: int = Field(default=0, ge=0)


class VisionSettings(_Section):
    """Computer-vision pipeline settings (Module 7).

    Disabled by default: vision analysis is heavy, so the operator turns it on
    once a real observer feed is being captured. The analytic (classical-CV)
    detectors need no model; an optional ONNX ``model_path`` enables the
    model-backed object detector for production-grade accuracy.
    """

    enabled: bool = False
    use_gpu: bool = True
    process_fps: int = Field(
        default=12, ge=1, le=120, description="Vision analysis rate (throttled below capture FPS)."
    )
    min_confidence: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Discard detections below this confidence."
    )
    downscale_width: int = Field(
        default=640, ge=64, le=3840, description="Analyse frames downscaled to this width."
    )

    # Per-detector toggles.
    detect_flash: bool = True
    detect_smoke: bool = True
    detect_fire: bool = True
    detect_kill_feed: bool = True
    detect_bomb_timer: bool = True
    detect_hud: bool = True
    detect_scene: bool = True

    # Optional ONNX object-detection model (weights are provided by the user).
    model_path: str = Field(default="", description="Path to an ONNX detection model (optional).")


class AISettings(_Section):
    """Commentary AI provider/model selection (M6)."""

    provider: AIProvider = AIProvider.MOCK
    play_by_play_model: str = Field(default="", description="Model id for the play-by-play AI.")
    analyst_model: str = Field(default="", description="Model id for the analyst AI.")
    api_key: str = Field(default="", description="Provider API key (blank uses env/local).")


class CommentarySettings(_Section):
    """High-level broadcast behaviour (Commentary Director, M5)."""

    language: Language = Language.ENGLISH
    excitement: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Baseline energy for play-by-play."
    )
    speech_delay_ms: int = Field(
        default=0, ge=0, le=10000, description="Broadcast delay applied before speaking."
    )
    allow_interruptions: bool = True
    min_speech_gap_ms: int = Field(
        default=800,
        ge=0,
        le=10000,
        description="Minimum gap between non-interrupting directives (rate limiting).",
    )


class LicensingSettings(_Section):
    """Account / licensing client settings (M8). No payment processing yet."""

    server_url: str = Field(default="", description="Licensing API base URL (blank = offline).")
    offline_cache_days: int = Field(
        default=14, ge=0, description="How long a cached license stays valid offline."
    )
    device_name: str = Field(default="", description="Friendly name for this device.")


class StatisticsSettings(_Section):
    """Statistics engine settings (M2)."""

    enabled: bool = True
    persist: bool = True


class LoggingSettings(_Section):
    """Logging & diagnostics settings (Module 20)."""

    level: str = Field(default="INFO")
    log_to_file: bool = True
    max_file_mb: int = Field(default=10, ge=1, le=1024)
    backup_count: int = Field(default=5, ge=0, le=100)

    @field_validator("level")
    @classmethod
    def _valid_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"level must be one of {sorted(allowed)}")
        return upper


class HotkeySettings(_Section):
    """Global hotkeys (wired up with the full UI in M9)."""

    toggle_casting: str = "Ctrl+Alt+C"
    mute_all: str = "Ctrl+Alt+M"
    force_replay_mode: str = "Ctrl+Alt+R"


class AppSettings(_Section):
    """Root settings document. One instance is the whole configuration."""

    schema_version: int = Field(default=1, description="Migration version for settings files.")
    gsi: GSISettings = Field(default_factory=GSISettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    audio_obs: OBSSettings = Field(default_factory=OBSSettings)
    replay: ReplaySettings = Field(default_factory=ReplaySettings)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    ai: AISettings = Field(default_factory=AISettings)
    commentary: CommentarySettings = Field(default_factory=CommentarySettings)
    licensing: LicensingSettings = Field(default_factory=LicensingSettings)
    statistics: StatisticsSettings = Field(default_factory=StatisticsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    hotkeys: HotkeySettings = Field(default_factory=HotkeySettings)
