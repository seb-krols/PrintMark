"""Read-only access to the local CSV history. Paths from records are never executed."""

from __future__ import annotations

import csv
from pathlib import Path

from .errors import SafeSkip

LOG_FIELDS = [
    "transaction",
    "id",
    "timestamp",
    "material",
    "gcode_filename",
    "object_names",
    "computer",
    "layers",
    "text_height_mm",
    "removed_filament_mm",
    "sha256",
]


def read_log(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != LOG_FIELDS:
                raise SafeSkip(
                    "log header is incompatible; preserve it and choose a new CSV log file"
                )
            rows = list(reader)
        if any(
            None in row
            or any(value is None for value in row.values())
            or not row["id"]
            or not row["transaction"]
            for row in rows
        ):
            raise SafeSkip("audit log has incomplete records; restore its backup before stamping")
        return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SafeSkip(f"cannot read audit log: {exc}") from exc


def lookup_id(path: Path, part_id: str) -> list[dict[str, str]]:
    part_id = part_id.strip()
    if not part_id:
        raise SafeSkip("enter the complete printed ID, including its prefix and leading zeros")
    return [row for row in read_log(path) if row["id"] == part_id]


def format_records(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No matching ID in this log. Check the prefix, leading zeros and the originating PC."
    records = []
    for row in rows:
        records.append(
            f"{row['id']} · {row['material']}\n"
            f"Exported (UTC): {row['timestamp']}\n"
            f"G-code: {row['gcode_filename']}\n"
            f"Objects: {row['object_names']}\n"
            f"Computer: {row['computer']}\n"
            f"Stamp: {row['layers']} layers, {row['text_height_mm']} mm text\n"
            f"Output SHA-256: {row['sha256']}"
        )
    prefix = (
        "Multiple records share this ID; investigate before identifying the part.\n\n"
        if len(rows) > 1
        else ""
    )
    return prefix + "\n\n".join(records)
