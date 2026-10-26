"""A bounded local last-export report, without copying the slicer environment."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from . import __version__
from .config import atomic_write, load_settings, validate_paths
from .env import metadata


def record_export(
    config: Path, source: Path, outcome, overrides: dict, env: dict[str, str]
) -> None:
    try:
        # Resolve the same storage paths as the export before opening any report lock.
        notes = env.get("SLIC3R_FILAMENT_NOTES")
        if notes is None:
            notes = metadata(source.read_text(encoding="utf-8", errors="replace")).get(
                "FILAMENT_NOTES", ""
            )
        settings = load_settings(config, notes, overrides)
        validate_paths(config, settings, source)
        target = config.parent / "last-export.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        report = asdict(outcome) | {
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            # PrusaSlicer runs the hook on a temporary file; show the name being exported.
            "source": env.get("SLIC3R_PP_OUTPUT_NAME") or str(source),
        }
        with FileLock(str(target) + ".lock", timeout=0.1):
            atomic_write(target, json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
    except Exception:
        # Diagnostic failure must never turn a successful export into a retry.
        print("BaseMark: could not save the last-export report.", file=sys.stderr)


def read_report(config: Path) -> str:
    path = config.parent / "last-export.json"
    if not path.exists():
        return "No export recorded yet. Export a job from PrusaSlicer to see its result here."
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        return (
            f"{report['status'].upper()} · {report['timestamp']}\n\n"
            f"{report['message']}\n\nSource: {report['source']}"
        )
    except (OSError, ValueError, KeyError, TypeError):
        return "The last-export report could not be read. Your counter and audit log are separate."
