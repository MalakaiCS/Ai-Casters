"""FastAPI transport for the replay receiver.

Exposes an HTTP endpoint the external replay system POSTs events to, running
uvicorn on a background thread so it never blocks the UI. Mirrors the GSI
transport so both integrations behave and test the same way.
"""

from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Request, Response

from ai_caster.core.interfaces import Service
from ai_caster.core.logging import get_logger
from ai_caster.replay.receiver import ReplayEventError, ReplayReceiver

_log = get_logger("replay.server")


def create_replay_app(receiver: ReplayReceiver) -> FastAPI:
    """Build the FastAPI app that feeds ``receiver``."""
    app = FastAPI(title="AI Esports Caster — Replay", version="1", docs_url=None, redoc_url=None)

    @app.post("/")
    async def ingest(request: Request) -> Response:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - malformed body
            return Response(status_code=400)
        if not isinstance(payload, dict):
            return Response(status_code=400)
        try:
            receiver.handle_event(payload)
        except ReplayEventError:
            return Response(status_code=422)
        except Exception:  # noqa: BLE001 - never let one event kill the server
            _log.exception("Error handling replay event")
            return Response(status_code=400)
        return Response(status_code=200)

    @app.get("/health")
    async def health() -> dict:
        state = receiver.state
        return {"status": "ok", "replay_active": state.active, "speed": state.speed}

    return app


class ReplayServer(Service):
    """Runs :func:`create_replay_app` under uvicorn on a background thread."""

    def __init__(
        self, receiver: ReplayReceiver, *, host: str = "127.0.0.1", port: int = 3112
    ) -> None:
        self._receiver = receiver
        self._host = host
        self._port = port
        self._app = create_replay_app(receiver)
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}/"

    def start(self) -> None:
        if self.is_running:
            return
        import uvicorn

        config = uvicorn.Config(
            self._app, host=self._host, port=self._port, log_level="warning", access_log=False
        )
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None
        self._thread = threading.Thread(target=self._server.run, name="replay-server", daemon=True)
        self._thread.start()
        self._wait_until_started()
        _log.info("Replay server listening on %s", self.address)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        self._server = None
        _log.info("Replay server stopped")

    def _wait_until_started(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server is not None and getattr(self._server, "started", False):
                return
            time.sleep(0.02)
        _log.warning("Replay server did not report started within %.1fs", timeout)
