"""Command-line entry point: ``ai-caster`` / ``python -m ai_caster``.

Subcommands:
- (default) launch the desktop application.
- ``gsi-config`` write the CS2 GSI config file.
- ``train`` run the offline training pipeline over authorized transcripts.
- ``version`` print the version.

The desktop UI is imported lazily so the ``gsi-config``/``train``/``version``
commands work in a headless environment without PySide6 installed.
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


def _cmd_train(args: argparse.Namespace) -> int:
    from pathlib import Path

    from ai_caster.training.guardrails import AudioInputRejected, AuthorizationError
    from ai_caster.training.pipeline import TrainingPipeline

    pipeline = TrainingPipeline()
    print("Training policy:")
    print(f"  {pipeline.policy}\n")

    directory = Path(args.sources)
    if not directory.is_dir():
        print(f"Not a directory: {directory}", file=sys.stderr)
        return 2

    # Unauthorized/audio-bearing sources raise here unless --skip-unauthorized.
    try:
        added = pipeline.add_directory(directory, skip_unauthorized=args.skip_unauthorized)
    except (AudioInputRejected, AuthorizationError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        print("Re-run with --skip-unauthorized to skip such files.", file=sys.stderr)
        return 1
    if added == 0:
        print("No authorized transcripts found; nothing to analyse.", file=sys.stderr)
        return 1

    profile = pipeline.run()
    print(pipeline.summary(profile))
    print(
        f"\nSuggested Director settings (review before adopting): "
        f"{pipeline.suggested_director_settings(profile)}"
    )

    if args.out:
        out = Path(args.out)
        pipeline.save_profile(profile, out)
        print(f"\nWrote style profile to {out}")
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

    p_train = sub.add_parser(
        "train",
        help="Offline: analyse AUTHORIZED transcripts for general pacing/vocabulary.",
    )
    p_train.add_argument("sources", help="Directory of authorized transcript *.json files.")
    p_train.add_argument("--out", help="Path to write the style-profile JSON to.")
    p_train.add_argument(
        "--skip-unauthorized",
        action="store_true",
        help="Skip unauthorized/audio-bearing files instead of failing.",
    )
    p_train.set_defaults(func=_cmd_train)

    p_ver = sub.add_parser("version", help="Print the version and exit.")
    p_ver.set_defaults(func=lambda _a: print(f"AI Esports Caster {__version__}") or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
