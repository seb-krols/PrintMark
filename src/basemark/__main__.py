from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .config import atomic_write, config_dir, load_settings, validate_paths
from .env import diagnostic_env
from .errors import SafeSkip


def parser():
    p = argparse.ArgumentParser(description="BaseMark — material identity, printed in.")
    p.add_argument(
        "gcode", nargs="?", type=Path, help="PrusaSlicer temporary G-code file (modified in place)"
    )
    p.add_argument("--version", action="version", version=f"BaseMark {__version__}")
    p.add_argument("--config", type=Path, default=config_dir() / "config.toml")
    action = p.add_mutually_exclusive_group()
    action.add_argument("--settings", action="store_true", help="open the settings window")
    action.add_argument("--lookup", metavar="ID", help="find a printed ID in the local CSV log")
    p.add_argument("--json", action="store_true", help="machine-readable output for --lookup")
    action.add_argument(
        "--check", action="store_true", help="check a job without stamping; exit 2 if unsupported"
    )
    action.add_argument(
        "--recover-from", type=Path, help="recover a pending audit from a matching final export"
    )
    action.add_argument(
        "--demo", action="store_true", help="try placement without a printer or G-code file"
    )
    p.add_argument("--off", dest="enabled", action="store_false", default=None)
    p.add_argument("--on", dest="enabled", action="store_true")
    p.add_argument("--mode", choices=["auto", "interactive"])
    p.add_argument("--size", dest="text_height_mm", type=float)
    p.add_argument("--min-size", dest="min_text_height_mm", type=float)
    p.add_argument("--layers", type=int)
    p.add_argument("--margin", dest="margin_mm", type=float)
    p.add_argument("--template")
    p.add_argument("--prefix", dest="counter_prefix")
    p.add_argument("--counter-next", type=int)
    p.add_argument("--counter-digits", type=int)
    p.add_argument("--counter-file")
    p.add_argument("--log-file")
    p.add_argument(
        "--dry-run", action="store_true", help="inspect only; no file edit or ID consumption"
    )
    p.add_argument("--preview-output", type=Path, help="save an underside SVG of the placement")
    action.add_argument(
        "--dump-env", action="store_true", help="write relevant SLIC3R settings; do not stamp"
    )
    action.add_argument(
        "--dump-all-env", action="store_true", help="include all SLIC3R keys (may include secrets)"
    )
    p.add_argument("--diagnostics-output", type=Path, help="environment JSON destination")
    return p


def main(argv=None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.json and args.lookup is None:
        cli.error("--json requires --lookup ID")
    if args.gcode and (args.lookup is not None or args.recover_from or args.settings or args.demo):
        cli.error("this action does not accept a G-code argument")
    keys = (
        "enabled",
        "mode",
        "text_height_mm",
        "min_text_height_mm",
        "layers",
        "margin_mm",
        "template",
        "counter_prefix",
        "counter_next",
        "counter_digits",
        "counter_file",
        "log_file",
    )
    overrides = {key: getattr(args, key) for key in keys}

    def report(outcome):
        if args.gcode and not (args.dry_run or args.check):
            from .diagnostics import record_export

            record_export(args.config, args.gcode, outcome, overrides, dict(os.environ))

    try:
        if args.lookup is not None:
            from .audit import format_records, lookup_id

            settings = load_settings(args.config, overrides=overrides)
            _, log = settings.paths(args.config.parent)
            rows = lookup_id(log, args.lookup)
            print(json.dumps(rows, indent=2) if args.json else format_records(rows))
            return 0 if rows else 1
        if args.recover_from:
            from .counter import Counter

            settings = load_settings(args.config)
            validate_paths(args.config, settings, args.recover_from)
            counter_path, _ = settings.paths(args.config.parent)
            with Counter(counter_path, settings.counter_next, recover=False) as counter:
                counter.recover_from(args.recover_from)
            print("BaseMark: recovered the audit and counter; selected G-code was not modified.")
            return 0
        if args.check and args.gcode is None:
            parser().error("--check requires a G-code file")
        if args.dump_env or args.dump_all_env:
            destination = args.diagnostics_output or args.config.parent / "environment.json"
            validate_paths(args.config, load_settings(args.config), args.gcode, destination)
            atomic_write(destination, diagnostic_env(dict(os.environ), args.dump_all_env).encode())
            print(f"BaseMark: environment saved to {destination}; G-code unchanged.")
            return 0
        if args.demo:
            from .popup import choose_placement
            from .service import demo_data

            footprint, surface, placed, settings = demo_data()
            choose_placement(footprint, surface, placed, settings, "PETG", "A042", demo=True)
            return 0
        if args.settings or args.gcode is None:
            from .settings_ui import open_settings

            open_settings(args.config)
            return 0
        from .service import process

        outcome = process(
            args.gcode,
            args.config,
            overrides,
            dict(os.environ),
            dry_run=args.dry_run or args.check,
            preview=args.preview_output,
        )
        stream = sys.stderr if outcome.status == "stamped-pending-audit" else sys.stdout
        report(outcome)
        print(f"BaseMark: {outcome.message}", file=stream)
        return 0
    except KeyboardInterrupt:
        print(
            "BaseMark: cancelled. Any interrupted transaction will recover on the next run.",
            file=sys.stderr,
        )
        return 0
    except (SafeSkip, OSError, ValueError) as exc:
        from .service import Outcome

        report(Outcome("skipped", str(exc)))
        print(f"BaseMark: skipped — {exc}", file=sys.stderr)
        if args.check:
            return 2
        return 0 if args.gcode else 1
    except Exception as exc:
        from .service import Outcome

        report(Outcome("error", f"{type(exc).__name__}: {exc}"))
        print(f"BaseMark: skipped — unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.check:
            return 2
        return 0 if args.gcode else 1


if __name__ == "__main__":
    raise SystemExit(main())
