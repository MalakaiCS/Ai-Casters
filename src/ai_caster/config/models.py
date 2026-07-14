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
    """Per-channel voice settings. Each voice is fully independent (Module 13):
    its own output device, volume, mute, latency, compressor, EQ and limiter."""

    enabled: bool = True
    output_device: str = Field(
        default="", description="Windows audio output device name (blank = system default)."
    )
    voice_id: str = Field(default="", description="TTS voice id (blank = engine default).")
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    muted: bool = False
    latency_ms: int = Field(default=120, ge=0, le=2000)

    # Per-channel dynamics/EQ (values are multipliers/normalised thresholds).
    compressor_enabled: bool = True
    compressor_threshold: float = Field(default=0.5, gt=0.0, le=1.0)
    compressor_ratio: float = Field(default=3.0, ge=1.0, le=20.0)
    eq_low: float = Field(default=1.0, ge=0.0, le=4.0)
    eq_mid: float = Field(default=1.0, ge=0.0, le=4.0)
    eq_high: float = Field(default=1.0, ge=0.0, le=4.0)
    limiter_ceiling: float = Field(default=0.95, gt=0.0, le=1.0)


class VoiceSettings(_Section):
    """Two independent voice channels plus a combined monitor mix (Module 14)."""

    play_by_play: VoiceChannelSettings = Field(default_factory=VoiceChannelSettings)
    analyst: VoiceChannelSettings = Field(default_factory=VoiceChannelSettings)
    monitor_device: str = Field(
        default="", description="Device for the combined monitor mix (e.g. headphones)."
    )
    monitor_volume: float = Field(default=0.8, ge=0.0, le=1.0)
    sample_rate: int = Field(default=24000, ge=8000, le=48000)
    tts_engine: str = Field(
        default="synthetic", description="TTS engine: 'synthetic' (offline) or 'system'."
    )


class OBSSettings(_Section):
    """OBS WebSocket integration (Module 16)."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=4455, ge=1, le=65535)
    password: str = ""
    auto_switch_scenes: bool = Field(
        default=False, description="Switch OBS scenes automatically on replay start/end."
    )
    live_scene: str = Field(default="Live", description="OBS scene name for live play.")
    replay_scene: str = Field(default="Replay", description="OBS scene name during replays.")


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
    detect_replay_text: bool = True

    # Region of the on-screen "REPLAY" banner, as fractions of the frame. Adjust
    # to match the broadcast overlay's placement.
    replay_region_left: float = Field(default=0.35, ge=0.0, le=1.0)
    replay_region_top: float = Field(default=0.02, ge=0.0, le=1.0)
    replay_region_width: float = Field(default=0.30, gt=0.0, le=1.0)
    replay_region_height: float = Field(default=0.09, gt=0.0, le=1.0)

    # Optional ONNX object-detection model (weights are provided by the user).
    model_path: str = Field(default="", description="Path to an ONNX detection model (optional).")


class AISettings(_Section):
    """Commentary AI provider/model selection (Module 11/12).

    Defaults to the deterministic MOCK provider so commentary runs offline with
    no API key. Selecting a real provider uses the official SDK; per-role model
    ids (blank = the provider's default) let play-by-play run on a faster model
    than the analyst if desired.
    """

    provider: AIProvider = AIProvider.MOCK
    play_by_play_model: str = Field(default="", description="Model id for the play-by-play AI.")
    analyst_model: str = Field(default="", description="Model id for the analyst AI.")
    api_key: str = Field(default="", description="Provider API key (blank uses env/local).")
    base_url: str = Field(default="", description="Override base URL (OpenAI-compatible/local).")
    max_tokens: int = Field(
        default=90, ge=16, le=1024, description="Max tokens per generated commentary line."
    )


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


class AccountProvider(StrEnum):
    """Which authentication backend the account client uses."""

    OFFLINE = "offline"  # deterministic local auth, no server (default)
    SUPABASE = "supabase"  # Supabase Auth (GoTrue)
    HTTP = "http"  # a generic custom JSON/HTTP account service


class AccountSettings(_Section):
    """Authentication client settings (Module 3, M8).

    ``provider`` selects the backend. ``offline`` (default) authenticates locally
    so the account surface works with no server. ``supabase`` uses Supabase Auth —
    set ``supabase_url`` and ``supabase_anon_key`` (the anon key is public and safe
    to ship; never embed the service-role key). ``http`` uses ``server_url`` for a
    custom service. ``remember`` persists the session; ``auto_login`` restores it.
    """

    provider: AccountProvider = AccountProvider.OFFLINE
    supabase_url: str = Field(
        default="", description="Supabase project URL (https://xxx.supabase.co)."
    )
    supabase_anon_key: str = Field(default="", description="Supabase anon/public API key.")
    server_url: str = Field(default="", description="Custom account API base URL (http provider).")
    remember: bool = Field(default=True, description="Persist the session across restarts.")
    auto_login: bool = Field(default=True, description="Restore a saved session on startup.")


class LicensingSettings(_Section):
    """Licensing client settings (Module 4, M8). No payment processing yet."""

    server_url: str = Field(default="", description="Licensing API base URL (blank = offline).")
    offline_cache_days: int = Field(
        default=14, ge=0, description="How long a cached license stays valid offline."
    )
    device_name: str = Field(default="", description="Friendly name for this device.")


class UpdaterSettings(_Section):
    """Auto-updater settings (Module 19, M8).

    Blank ``manifest_url`` selects the offline (null) backend, which never reports
    an update. ``{channel}`` in the URL is substituted with ``channel``.
    """

    enabled: bool = Field(default=True, description="Allow update checks.")
    manifest_url: str = Field(default="", description="Release manifest URL (blank = offline).")
    channel: str = Field(default="stable", description="Release channel to track.")
    auto_check: bool = Field(default=True, description="Check for updates on startup.")


class SyncSettings(_Section):
    """Cloud settings-sync settings (M8).

    Requires the CLOUD_SYNC entitlement and sign-in. Blank ``server_url`` selects
    the local no-op backend.
    """

    enabled: bool = Field(default=False, description="Enable cloud settings sync.")
    server_url: str = Field(default="", description="Sync API base URL (blank = offline no-op).")
    auto_sync: bool = Field(default=True, description="Pull on sign-in and push on change.")


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
    """Global hotkeys (Module 1 completion, M9).

    ``enabled`` gates OS-level global hotkey registration; when off (or when the
    optional backend is unavailable) the same actions remain reachable from the UI.
    """

    enabled: bool = Field(default=True, description="Register OS-global hotkeys.")
    toggle_casting: str = "Ctrl+Alt+C"
    mute_all: str = "Ctrl+Alt+M"
    force_replay_mode: str = "Ctrl+Alt+R"


class DiagnosticsSettings(_Section):
    """Runtime diagnostics dashboard (Module 20 completion, M9)."""

    enabled: bool = Field(default=True, description="Publish periodic diagnostics snapshots.")
    poll_interval_seconds: float = Field(
        default=2.0, ge=0.25, le=60.0, description="How often to sample runtime health."
    )
    log_tail_lines: int = Field(
        default=200, ge=10, le=5000, description="Lines shown in the in-app log inspector."
    )


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
    account: AccountSettings = Field(default_factory=AccountSettings)
    licensing: LicensingSettings = Field(default_factory=LicensingSettings)
    updater: UpdaterSettings = Field(default_factory=UpdaterSettings)
    sync: SyncSettings = Field(default_factory=SyncSettings)
    statistics: StatisticsSettings = Field(default_factory=StatisticsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    hotkeys: HotkeySettings = Field(default_factory=HotkeySettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
