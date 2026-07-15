"""Composition root — dependency injection for the whole application.

Nothing in the feature modules constructs its own collaborators; they receive
them. This file is the single place where concrete implementations are created
and wired together, which keeps every module independently testable and makes
the system's shape explicit.

The :class:`Application` deliberately contains **no UI code**. The desktop shell
(``ai_caster.ui``) is layered on top of it, so the core application can also be
driven headlessly (tests, a future server/CLI mode).
"""

from __future__ import annotations

import importlib.util
import logging

from ai_caster import __version__
from ai_caster.auth.client import AuthClient
from ai_caster.auth.factory import create_auth_backend
from ai_caster.auth.store import SessionStore
from ai_caster.auth.team import create_team_client
from ai_caster.broadcast.controller import BroadcastController
from ai_caster.capture.factory import create_frame_source
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.uploader import create_uploader
from ai_caster.commentary.factory import create_provider
from ai_caster.commentary.generator import CommentaryGenerator
from ai_caster.config.deploy import deploy_overrides
from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import AppSettings
from ai_caster.core.events import EventBus, GSIConnectionChanged
from ai_caster.core.identity import get_or_create_device_id
from ai_caster.core.logging import configure_logging, get_logger
from ai_caster.core.paths import AppPaths, get_app_paths
from ai_caster.diagnostics.collector import DiagnosticsCollector, DiagnosticsSources
from ai_caster.diagnostics.engine import DiagnosticsEngine
from ai_caster.director.directives import Speaker
from ai_caster.director.director import CommentaryDirector
from ai_caster.gsi.receiver import GSIReceiver
from ai_caster.gsi.server import GSIServer
from ai_caster.hotkeys.actions import HotkeyAction
from ai_caster.hotkeys.backend import NullHotkeyBackend, PynputHotkeyBackend
from ai_caster.hotkeys.manager import HotkeyManager
from ai_caster.licensing.cache import LicenseCache
from ai_caster.licensing.client import LicensingClient
from ai_caster.licensing.factory import create_licensing_backend
from ai_caster.match.engine import MatchStateEngine
from ai_caster.match.state import MatchStateStore
from ai_caster.obs.controller import NullOBSController, WebSocketOBSController
from ai_caster.obs.integration import OBSIntegration
from ai_caster.persistence.database import Database
from ai_caster.persistence.repository import MatchRepository
from ai_caster.replay.receiver import ReplayReceiver
from ai_caster.replay.server import ReplayServer
from ai_caster.statistics.engine import StatisticsEngine
from ai_caster.sync.client import SettingsSyncClient
from ai_caster.sync.factory import create_sync_backend
from ai_caster.updater.backend import HttpUpdateBackend, NullUpdateBackend
from ai_caster.updater.updater import AutoUpdater
from ai_caster.vision.factory import create_vision_pipeline
from ai_caster.voice.engine import VoiceEngine


class Application:
    """Owns and wires the long-lived services that make up the app core."""

    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = (paths or get_app_paths()).ensure()

        # --- settings first, so logging honours the configured level ------ #
        self.event_bus = EventBus()
        self.settings_manager = SettingsManager(self.paths.settings_file, self.event_bus)
        settings: AppSettings = self.settings_manager.load()

        # --- logging (Module 20) ------------------------------------------ #
        log_dir = self.paths.log_dir if settings.logging.log_to_file else None
        configure_logging(
            log_dir=log_dir,
            level=getattr(logging, settings.logging.level, logging.INFO),
            max_bytes=settings.logging.max_file_mb * 1024 * 1024,
            backup_count=settings.logging.backup_count,
        )
        self._log = get_logger("app")
        self._log.info("Initialising %s core", "AI Esports Caster")

        # --- match state (single source of truth foundation) -------------- #
        self.match_store = MatchStateStore()

        # --- GSI receiver + transport (Module 5) -------------------------- #
        self.gsi_receiver = GSIReceiver(
            self.event_bus,
            self.match_store,
            auth_token=settings.gsi.auth_token,
            require_auth=settings.gsi.require_auth,
        )
        self.gsi_server = GSIServer(
            self.gsi_receiver,
            host=settings.gsi.host,
            port=settings.gsi.port,
        )

        # --- persistence (M2, optional) ----------------------------------- #
        self.database: Database | None = None
        repository: MatchRepository | None = None
        if settings.statistics.enabled and settings.statistics.persist:
            self.database = Database(self.paths.data_dir / "ai_caster.sqlite")
            repository = MatchRepository(self.database)

        # --- statistics + match engine (Modules 17, 8, 9) ----------------- #
        self.statistics = StatisticsEngine()
        self.match_engine = MatchStateEngine(
            self.event_bus,
            self.statistics,
            repository=repository,
            persist=settings.statistics.persist,
        )

        # --- video capture (Module 6) ------------------------------------- #
        # Built but NOT auto-started: capture is a heavy subsystem the operator
        # turns on (from the UI) once the observer feed is ready.
        self.capture = CapturePipeline(
            create_frame_source(settings.capture),
            self.event_bus,
            target_fps=settings.capture.target_fps,
            buffer_size=settings.capture.buffer_size,
            uploader=create_uploader(settings.capture.use_gpu),
        )

        # --- computer vision (Module 7) ----------------------------------- #
        # Consumes captured frames; disabled by default until the operator turns
        # it on. Attached to the capture pipeline as a frame callback.
        self.vision = create_vision_pipeline(settings.vision, self.event_bus)
        self.vision.attach(self.capture)

        # --- replay integration (Module 15) ------------------------------- #
        self.replay_receiver = ReplayReceiver(self.event_bus)
        self.replay_server = ReplayServer(
            self.replay_receiver, host="127.0.0.1", port=settings.replay.listen_port
        )

        # --- commentary director (Module 10) ------------------------------ #
        self.director = CommentaryDirector(
            self.event_bus,
            baseline_excitement=settings.commentary.excitement,
            allow_interruptions=settings.commentary.allow_interruptions,
            min_speech_gap=settings.commentary.min_speech_gap_ms / 1000.0,
            replay_integration_enabled=settings.replay.enabled,
            treat_unknown_as_live=settings.replay.treat_unknown_as_live,
        )

        # --- commentary AIs (Modules 11 & 12) ----------------------------- #
        # Two independent generators sharing one provider; each turns the
        # directives addressed to its role into spoken lines on a worker thread.
        provider = create_provider(settings.ai)
        language = settings.commentary.language.value
        self.play_by_play = CommentaryGenerator(
            self.event_bus,
            provider,
            Speaker.PLAY_BY_PLAY,
            model=settings.ai.play_by_play_model,
            language=language,
            max_tokens=settings.ai.max_tokens,
        )
        self.analyst = CommentaryGenerator(
            self.event_bus,
            provider,
            Speaker.ANALYST,
            model=settings.ai.analyst_model,
            language=language,
            max_tokens=settings.ai.max_tokens,
        )

        # --- voice engine + audio routing (Modules 13 & 14) --------------- #
        # Subscribes to generated lines; offline synthetic TTS + null sinks by
        # default (real devices used only when configured and available).
        self.voice = VoiceEngine(self.event_bus, settings.voice)

        # --- OBS integration (Module 16) ---------------------------------- #
        obs_available = importlib.util.find_spec("obsws_python") is not None
        if settings.audio_obs.enabled and obs_available:
            controller = WebSocketOBSController(
                host=settings.audio_obs.host,
                port=settings.audio_obs.port,
                password=settings.audio_obs.password,
            )
        else:
            controller = NullOBSController()
        self.obs = OBSIntegration(
            self.event_bus,
            controller,
            auto_switch_scenes=settings.audio_obs.auto_switch_scenes,
            live_scene=settings.audio_obs.live_scene,
            replay_scene=settings.audio_obs.replay_scene,
        )

        # --- accounts, licensing, updates, sync (Modules 3, 4, 19; M8) ---- #
        # Each subsystem defaults to an offline backend so the whole account
        # surface works with no server; an HTTP backend is selected only when the
        # matching service URL is configured. A stable per-install device id ties
        # sessions and license seats together.
        self.device_id = get_or_create_device_id(self.paths.config_dir)

        self.auth = AuthClient(
            self.event_bus,
            create_auth_backend(settings.account),
            device_id=self.device_id,
            store=SessionStore(self.paths.config_dir / "session.json"),
            remember=settings.account.remember,
        )

        # Team roster / role management (Admin+); no-op unless Supabase-backed.
        self.team = create_team_client(settings.account)

        self.licensing = LicensingClient(
            self.event_bus,
            create_licensing_backend(settings.licensing, settings.account),
            device_id=self.device_id,
            cache=LicenseCache(self.paths.cache_dir / "license.json"),
            offline_cache_days=settings.licensing.offline_cache_days,
        )

        # Fall back to the build-baked manifest URL when the user's settings file
        # predates it (an upgrade over an older install), so updates keep working.
        manifest_url = settings.updater.manifest_url or deploy_overrides().get("updater", {}).get(
            "manifest_url", ""
        )
        update_backend = HttpUpdateBackend(manifest_url) if manifest_url else NullUpdateBackend()
        self.updater = AutoUpdater(
            self.event_bus,
            update_backend,
            current_version=__version__,
            channel=settings.updater.channel,
            cache_dir=self.paths.cache_dir,
        )

        self.sync = SettingsSyncClient(
            self.event_bus,
            create_sync_backend(settings.sync, settings.account),
            self.settings_manager,
            self.auth,
            self.licensing,
            enabled=settings.sync.enabled,
        )

        # --- broadcast control + hotkeys (Module 1 completion; M9) -------- #
        # One switch for the whole cast, shared by the UI and the global hotkeys,
        # and gated on the live-casting entitlement.
        self.broadcast = BroadcastController(
            self.event_bus,
            capture=self.capture,
            vision=self.vision,
            voice=self.voice,
            licensing=self.licensing,
        )
        hotkey_backend = (
            PynputHotkeyBackend()
            if settings.hotkeys.enabled and importlib.util.find_spec("pynput") is not None
            else NullHotkeyBackend()
        )
        self.hotkeys = HotkeyManager(
            settings.hotkeys,
            {
                HotkeyAction.TOGGLE_CASTING: self.broadcast.toggle_casting,
                HotkeyAction.MUTE_ALL: self.broadcast.toggle_mute,
                HotkeyAction.FORCE_REPLAY_MODE: self.broadcast.toggle_forced_replay,
            },
            backend=hotkey_backend,
        )

        # --- diagnostics dashboard (Module 20 completion; M9) ------------- #
        # Reads live state through accessor callables so the collector stays
        # decoupled from the subsystems it samples.
        self._gsi_connected = False
        self.event_bus.subscribe(GSIConnectionChanged, self._on_gsi_connection)
        diagnostics_sources = DiagnosticsSources(
            gsi_connected=lambda: self._gsi_connected,
            capture_stats=lambda: self.capture.stats() if self.capture else None,
            vision_enabled=lambda: self.vision.enabled,
            vision_processed=lambda: self.vision.processed_count,
            voice_pending=lambda: (
                self.voice.play_by_play.pending(),
                self.voice.analyst.pending(),
            ),
            # The Director reflects the *effective* replay state (external replay
            # events and forced replay mode alike), so it's the honest source here.
            replay_active=lambda: self.director.replay_active,
            casting=lambda: self.broadcast.is_casting,
            muted=lambda: self.broadcast.is_muted,
        )
        self.diagnostics = DiagnosticsEngine(
            self.event_bus,
            DiagnosticsCollector(sources=diagnostics_sources),
            poll_interval=settings.diagnostics.poll_interval_seconds,
        )

        # Re-apply GSI auth whenever settings change so edits take effect live.
        self.settings_manager.add_observer(self._on_settings_changed)

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #
    @property
    def settings(self) -> AppSettings:
        return self.settings_manager.settings

    def start_services(self) -> None:
        """Start all background services (GSI server, and the replay server when
        replay integration is enabled)."""
        self.gsi_server.start()
        if self.settings.replay.enabled:
            self.replay_server.start()
        self.play_by_play.start()
        self.analyst.start()
        self.voice.start()
        if self.settings.audio_obs.enabled:
            self.obs.connect()
        self._start_account_services()
        if self.settings.hotkeys.enabled:
            self.hotkeys.start()
        if self.settings.diagnostics.enabled:
            self.diagnostics.start()
        self._log.info("Core services started")

    def _start_account_services(self) -> None:
        """Restore sign-in, validate the license, sync settings and check for
        updates — each guarded so a failure never blocks the broadcast."""
        if self.settings.account.auto_login:
            try:
                self.auth.restore()
            except Exception:  # noqa: BLE001 - sign-in must not block startup
                self._log.exception("Session restore failed")

        account_id = self.auth.account.user_id if self.auth.account else ""
        token = self.auth.session.access_token if self.auth.session else ""
        try:
            self.licensing.validate(account_id, token=token)
        except Exception:  # noqa: BLE001 - fall through to offline/free
            self._log.exception("License validation failed")

        if self.settings.sync.enabled and self.settings.sync.auto_sync:
            try:
                self.sync.pull()
            except Exception:  # noqa: BLE001 - sync is best-effort
                self._log.exception("Settings sync (pull) failed")

        if self.settings.updater.enabled and self.settings.updater.auto_check:
            try:
                self.updater.check()
            except Exception:  # noqa: BLE001 - update check is best-effort
                self._log.exception("Update check failed")

    def stop_services(self) -> None:
        """Stop all background services and release resources."""
        self.diagnostics.dispose()
        self.hotkeys.dispose()
        self.broadcast.dispose()
        self.gsi_server.stop()
        if self.replay_server.is_running:
            self.replay_server.stop()
        self.vision.detach()
        if self.capture.is_running:
            self.capture.stop()
        self.voice.dispose()
        self.obs.dispose()
        self.play_by_play.dispose()
        self.analyst.dispose()
        self.director.dispose()
        self.match_engine.dispose()
        if self.database is not None:
            self.database.close()
        self._log.info("Core services stopped")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _on_settings_changed(self, settings: AppSettings) -> None:
        self.gsi_receiver.update_auth(settings.gsi.auth_token, settings.gsi.require_auth)

    def _on_gsi_connection(self, event: GSIConnectionChanged) -> None:
        self._gsi_connected = event.connected
