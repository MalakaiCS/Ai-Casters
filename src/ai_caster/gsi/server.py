"""FastAPI transport for the GSI receiver.

CS2 delivers Game State Integration data by HTTP POST to a configured URL. This
module builds a small FastAPI app that forwards each payload to a
:class:`~ai_caster.gsi.receiver.GSIReceiver`, and wraps a uvicorn server so it
can run on a **background thread** — never blocking the Qt UI thread.

Separating this transport from the receiver keeps the domain logic testable with
Starlette's ``TestClient`` (no real socket needed) while production runs the same
app under uvicorn.
"""

from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Request, Response

from ai_caster.core.interfaces import Service
from ai_caster.core.logging import get_logger
from ai_caster.gsi.receiver import GSIAuthError, GSIReceiver

_log = get_logger("gsi.server")


def create_gsi_app(receiver: GSIReceiver) -> FastAPI:
    """Build the FastAPI app that feeds ``receiver``.

    CS2 does not read the HTTP response body, so endpoints return terse status
    codes: 200 on success, 401 on bad auth, 400 on unparseable payloads.
    """
    app = FastAPI(title="AI Esports Caster — GSI", version="1", docs_url=None, redoc_url=None)

    @app.post("/")
    async def ingest(request: Request) -> Response:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - malformed body from the game
            _log.warning("Received non-JSON GSI body")
            return Response(status_code=400)

        if not isinstance(payload, dict):
            return Response(status_code=400)

        try:
            receiver.handle_payload(payload)
        except GSIAuthError:
            return Response(status_code=401)
        except Exception:  # noqa: BLE001 - never let one bad payload kill the server
            _log.exception("Error handling GSI payload")
            return Response(status_code=400)
        return Response(status_code=200)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "payloads": receiver.payload_count,
            "last_payload_at": (
                receiver.last_payload_at.isoformat() if receiver.last_payload_at else None
            ),
        }

    return app


class GSIServer(Service):
    """Runs :func:`create_gsi_app` under uvicorn on a background thread.

    Implements :class:`~ai_caster.core.interfaces.Service` so the application can
    start/stop it uniformly. ``start``/``stop`` are idempotent.
    """

    def __init__(self, receiver: GSIReceiver, *, host: str = "127.0.0.1", port: int = 3111) -> None:
        self._receiver = receiver
        self._host = host
        self._port = port
        self._app = create_gsi_app(receiver)
        self._server = None  # type: ignore[assignment]  # uvicorn.Server, lazily imported
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}/"

    def start(self) -> None:
        """Bind and serve on a daemon thread. No-op if already running."""
        if self.is_running:
            return

        # Imported lazily so importing this module (e.g. for the app factory or
        # tests using TestClient) doesn't require uvicorn to spin up a loop.
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        # install_signal_handlers only works on the main thread.
        self._server.install_signal_handlers = lambda: None

        self._thread = threading.Thread(target=self._server.run, name="gsi-server", daemon=True)
        self._thread.start()
        self._wait_until_started()
        _log.info("GSI server listening on %s", self.address)

    def stop(self) -> None:
        """Signal uvicorn to exit and join the thread. No-op if not running."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                _log.warning("GSI server thread did not stop within timeout")
        self._thread = None
        self._server = None
        _log.info("GSI server stopped")

    def _wait_until_started(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server is not None and getattr(self._server, "started", False):
                return
            time.sleep(0.02)
        _log.warning("GSI server did not report started within %.1fs", timeout)
