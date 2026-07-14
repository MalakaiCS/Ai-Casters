"""PyInstaller entry point for the packaged Windows desktop app.

Kept tiny and separate from ``ai_caster.__main__`` so the frozen build launches
straight into the GUI (no argparse, no console). All real logic lives in the
``ai_caster`` package.
"""

from __future__ import annotations

import sys


def main() -> int:
    from ai_caster.ui.main_window import run_desktop_app

    return run_desktop_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
