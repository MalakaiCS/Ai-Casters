"""Command-line entry point: ``ai-caster`` / ``python -m ai_caster``.

Subcommands:
- (default) launch the desktop application.
- ``gsi-config`` write the CS2 GSI config file.
- ``version`` print the version.

The desktop UI is imported lazily so the ``gsi-config``/``version`` commands work
in a headless environment without PySide6 installed.
"""

from __future__ import annotations

import argparse
import sys

from ai_caster import __version__
from ai_caster.app import Application


def _cmd_gsi_config(args: argparse.Namespace) -> int:
    from ai_caster.gsi.cfg import build_gsi_config

    app = Application()
    gsi = app.settings.gsi
    text = build_gsi_config(host=gsi.host, port=gsi.port, auth_token=gsi.auth_token)
    if args.out:
        from pathlib import Path

        path = Path(args.out)
        path.write_text(text, encoding="utf-8")
        print(f"Wrote CS2 GSI config to {path}")
        print("Copy it into: .../Counter-Strike Global Offensive/game/csgo/cfg/")
    else:
        sys.stdout.write(text)
    return 0


def _cmd_run(_args: argparse.Namespace) -> int:
    try:
        from ai_caster.ui.main_window import run_desktop_app
    except ImportError as exc:  # PySide6 not installed
        print(f"Desktop UI unavailable: {exc}", file=sys.stderr)
        print('Install UI extras with:  pip install -e ".[ui]"', file=sys.stderr)
        return 2
    return run_desktop_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-caster", description="AI Esports Caster")
    parser.set_defaults(func=_cmd_run)
    sub = parser.add_subparsers(dest="command")

    p_cfg = sub.add_parser("gsi-config", help="Generate the CS2 GSI config file.")
    p_cfg.add_argument("--out", help="Path to write the .cfg to (defaults to stdout).")
    p_cfg.set_defaults(func=_cmd_gsi_config)

    p_ver = sub.add_parser("version", help="Print the version and exit.")
    p_ver.set_defaults(func=lambda _a: (print(f"AI Esports Caster {__version__}") or 0))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
