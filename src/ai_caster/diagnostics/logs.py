"""Log inspection for the in-app diagnostics view.

The rotating log file is size-bounded, so reading it whole and slicing the tail is
simple and cheap. Returns lines newest-last (file order).
"""

from __future__ import annotations

from pathlib import Path

LOG_FILENAME = "ai_caster.log"


def tail_log(log_dir: Path | None, *, lines: int = 200) -> list[str]:
    """Return the last ``lines`` lines of the application log, or [] if absent."""
    if log_dir is None:
        return []
    path = Path(log_dir) / LOG_FILENAME
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            all_lines = handle.read().splitlines()
    except OSError:
        return []
    if lines <= 0:
        return all_lines
    return all_lines[-lines:]
