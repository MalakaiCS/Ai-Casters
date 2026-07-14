"""Regression: the app must start when there is no console (windowed build).

A windowed PyInstaller build runs with ``sys.stdout``/``sys.stderr`` set to
``None``. uvicorn's default logging config calls ``sys.stdout.isatty()`` and
crashed the packaged app at GSI-server startup. These tests reproduce the
no-console environment and assert the servers and logging survive it.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_headless(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        timeout=60,
    )


def test_gsi_server_starts_without_console_streams():
    port = _free_port()
    result = _run_headless(f"""
        import sys
        sys.stdout = None
        sys.stderr = None
        from ai_caster.core.events import EventBus
        from ai_caster.match.state import MatchStateStore
        from ai_caster.gsi.receiver import GSIReceiver
        from ai_caster.gsi.server import GSIServer
        receiver = GSIReceiver(EventBus(), MatchStateStore(), auth_token="t", require_auth=False)
        server = GSIServer(receiver, host="127.0.0.1", port={port})
        server.start()
        assert server.is_running
        server.stop()
    """)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_replay_server_starts_without_console_streams():
    port = _free_port()
    result = _run_headless(f"""
        import sys
        sys.stdout = None
        sys.stderr = None
        from ai_caster.replay.receiver import ReplayReceiver
        from ai_caster.replay.server import ReplayServer
        server = ReplayServer(ReplayReceiver(), host="127.0.0.1", port={port})
        server.start()
        assert server.is_running
        server.stop()
    """)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_configure_logging_survives_missing_console(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stderr", None)
    from ai_caster.core.logging import configure_logging, get_logger

    root = configure_logging(log_dir=tmp_path, console=True)
    # No console handler was attached (nothing to write to), but a file handler is.
    assert all(not (type(h).__name__ == "StreamHandler") for h in root.handlers), (
        "console handler must not be attached when sys.stderr is None"
    )
    # Logging must not raise even though the console stream is absent.
    get_logger("test").info("no console here")
