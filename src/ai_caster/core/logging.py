"""Module 20 — Logging & Diagnostics.

Centralised logging configuration for the whole application. Everything is
**timestamped** (UTC, millisecond precision) and written both to the console and
to a rotating file inside the per-user log directory. Feature modules obtain a
logger with :func:`get_logger` and never configure logging themselves.

Design notes:
- One idempotent :func:`configure_logging` call at startup owns handler setup.
- A rotating file handler keeps long-duration broadcasts from filling the disk.
- A dedicated ``diagnostics`` logger namespace is reserved for latency/perf
  events so they can later be routed to a metrics sink without touching call
  sites.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_ROOT_LOGGER_NAME = "ai_caster"
_DEFAULT_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


class _UtcFormatter(logging.Formatter):
    """Formatter that renders timestamps in UTC for consistent broadcast logs."""

    import time as _time

    converter = staticmethod(_time.gmtime)


def configure_logging(
    log_dir: Path | None = None,
    *,
    level: int | str = logging.INFO,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configure the ``ai_caster`` logger tree. Idempotent.

    Parameters
    ----------
    log_dir:
        Directory for the rotating log file. If ``None`` no file handler is
        attached (useful for tests). The directory is created if missing.
    level:
        Root level for the application logger tree.
    console:
        Attach a stream handler to stderr.
    max_bytes / backup_count:
        Rotation policy for the file handler.
    """
    global _configured

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(level)
    # Don't propagate to the Python root logger — we own our handlers fully.
    root.propagate = False

    # Idempotency: clear our own handlers so repeat calls (e.g. tests) don't
    # duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = _UtcFormatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "ai_caster.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _configured = True
    root.debug("Logging configured (level=%s, file=%s)", logging.getLevelName(level), log_dir)
    return root


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the ``ai_caster`` namespace.

    ``get_logger("gsi.server")`` -> logger ``ai_caster.gsi.server``.
    Passing ``None`` returns the application root logger.
    """
    if not name:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def get_diagnostics_logger() -> logging.Logger:
    """Logger reserved for performance/latency/diagnostics events."""
    return get_logger("diagnostics")


def is_configured() -> bool:
    """Whether :func:`configure_logging` has run at least once."""
    return _configured
