"""PyInstaller entry point for the packaged Windows desktop app.

Kept tiny and separate from ``ai_caster.__main__`` so the frozen build launches
straight into the GUI (no argparse, no console). All real logic lives in the
``ai_caster`` package.
"""

from __future__ import annotations

import os
import sys


def _ensure_std_streams() -> None:
    """Give the process real stdout/stderr.

    A windowed PyInstaller build (``console=False``) sets ``sys.stdout`` and
    ``sys.stderr`` to ``None``. Any library that touches them (uvicorn's log
    formatter calls ``sys.stdout.isatty()``) would crash at startup. Point the
    missing streams at the null device so those calls succeed harmlessly; real
    diagnostics still go to the rotating log file.
    """
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            if devnull is None:
                devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            setattr(sys, name, devnull)


def main() -> int:
    _ensure_std_streams()
    from ai_caster.ui.main_window import run_desktop_app

    return run_desktop_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
