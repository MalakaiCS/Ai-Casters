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

import logging

from ai_caster.capture.factory import create_frame_source
from ai_caster.capture.pipeline import CapturePipeline
from ai_caster.capture.uploader import create_uploader
from ai_caster.config.manager import SettingsManager
from ai_caster.config.models import AppSettings
from ai_caster.core.events import EventBus
from ai_caster.core.logging import configure_logging, get_logger
from ai_caster.core.paths import AppPaths, get_app_paths
from ai_caster.gsi.receiver import GSIReceiver
from ai_caster.gsi.server import GSIServer
from ai_caster.match.engine import MatchStateEngine
from ai_caster.match.state import MatchStateStore
from ai_caster.persistence.database import Database
from ai_caster.persistence.repository import MatchRepository
from ai_caster.statistics.engine import StatisticsEngine
from ai_caster.vision.factory import create_vision_pipeline


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

        # Re-apply GSI auth whenever settings change so edits take effect live.
        self.settings_manager.add_observer(self._on_settings_changed)

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #
    @property
    def settings(self) -> AppSettings:
        return self.settings_manager.settings

    def start_services(self) -> None:
        """Start all background services (currently the GSI server)."""
        self.gsi_server.start()
        self._log.info("Core services started")

    def stop_services(self) -> None:
        """Stop all background services and release resources."""
        self.gsi_server.stop()
        self.vision.detach()
        if self.capture.is_running:
            self.capture.stop()
        self.match_engine.dispose()
        if self.database is not None:
            self.database.close()
        self._log.info("Core services stopped")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _on_settings_changed(self, settings: AppSettings) -> None:
        self.gsi_receiver.update_auth(settings.gsi.auth_token, settings.gsi.require_auth)
