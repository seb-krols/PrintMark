from __future__ import annotations

import socket
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings, atomic_write, load_settings, validate_paths
from .counter import Counter, digest
from .env import job_from, metadata
from .errors import SafeSkip
from .footprint import placement_surface
from .gcode_parser import parse
from .gcode_writer import rewrite
from .placement import auto_place
from .preview import svg_preview


@dataclass(frozen=True)
class Outcome:
    status: str
    message: str
    part_id: str = ""
    removed_e: float = 0
    changed_moves: int = 0


def read_gcode(path: Path) -> tuple[bytes, str]:
    if path.is_symlink():
        raise SafeSkip("symlink input is unsupported")
    data = path.read_bytes()
    if (
        path.suffix.lower() == ".bgcode"
        or data.startswith((b"GCDE", b"PK\x03\x04"))
        or b"\0" in data
    ):
        raise SafeSkip("binary/packaged G-code is unsupported; export plain text .gcode")
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SafeSkip("G-code must be UTF-8/ASCII text") from exc


def process(
    path: Path,
    config: Path,
    overrides: dict,
    env: dict[str, str],
    *,
    dry_run: bool = False,
    preview: Path | None = None,
    choose=None,
) -> Outcome:
    if overrides.get("enabled") is False:
        return Outcome("disabled", "BaseMark is off; file unchanged.")
    original, text = read_gcode(path)
    notes = env.get("SLIC3R_FILAMENT_NOTES")
    if notes is None:  # standalone use; scanning a large file's metadata is not free
        notes = metadata(text).get("FILAMENT_NOTES", "")
    settings = load_settings(config, notes, overrides)
    if not settings.enabled:
        return Outcome("disabled", "BaseMark is off; file unchanged.")
    job = job_from(env, text, settings, str(path))
    program = parse(text, job.width, retain_layers=settings.layers + 1)
    footprint, surface = placement_surface(program, settings.layers, settings.margin_mm)
    counter_path, log_path = settings.paths(config.parent)
    validate_paths(config, settings, path, preview)
    with Counter(counter_path, settings.counter_next, recover=not dry_run) as counter:
        if counter.state.get("pending"):
            raise SafeSkip("counter recovery is pending; open Settings → Diagnostics to recover")
        part_id = settings.counter_prefix + str(counter.next).zfill(settings.counter_digits)
        now = datetime.now(UTC)
        label = settings.template.format(
            material=job.material,
            id=part_id,
            prefix=settings.counter_prefix,
            date=now.date().isoformat(),
        )
        placed = auto_place(label, surface, settings.text_height_mm, settings.min_text_height_mm)
        if settings.mode == "interactive" and not dry_run:
            if choose is None:
                from .popup import choose_placement

                choose = choose_placement
            job_name = Path(job.output_name or path).name
            placed = choose(footprint, surface, placed, settings, job.material, part_id, job_name)
            if placed is None:
                from .notify import USER_SKIP

                return Outcome("skipped", USER_SKIP)
        if not placed.fits(surface):
            raise SafeSkip("placement is outside the solid surface or margin")
        output = rewrite(program, placed.geometry, settings.layers, part_id)
        with counter.guard_id(log_path, part_id):
            if preview:
                atomic_write(preview, svg_preview(footprint, surface, placed).encode("utf-8"))
            if dry_run:
                return Outcome(
                    "preview",
                    f"Preview {label}: {output.changed_moves} moves; no ID consumed.",
                    part_id,
                    output.removed_e,
                    output.changed_moves,
                )
            encoded = output.text.encode("utf-8")
            if path.read_bytes() != original:
                raise SafeSkip("G-code changed during placement; export again")
            row = {
                "transaction": uuid.uuid4().hex,
                "id": part_id,
                "timestamp": now.isoformat(),
                "material": job.material,
                "gcode_filename": job.output_name,
                "object_names": " | ".join(program.objects),
                "computer": socket.gethostname(),
                "layers": settings.layers,
                "text_height_mm": placed.height,
                "removed_filament_mm": round(output.removed_e, 7),
                "sha256": digest(encoded),
            }
            counter.prepare(path, original, encoded, row, log_path)
            try:
                atomic_write(path, encoded, mode=stat.S_IMODE(path.stat().st_mode))
            except OSError as exc:
                # A directory fsync can fail AFTER os.replace has committed the file.
                # Distinguish that case from failure before replacement.
                if path.read_bytes() == encoded:
                    return Outcome(
                        "stamped-pending-audit",
                        f"Stamped {label}; write durability/audit recovery pending ({exc}). "
                        "See docs/recovery.md.",
                        part_id,
                        output.removed_e,
                        output.changed_moves,
                    )
                counter.recover()
                raise
            try:
                counter.finish()
            except Exception as exc:
                # The source is already safely replaced. Retain the persisted journal
                # and report the distinction; do not falsely claim the file is unchanged.
                return Outcome(
                    "stamped-pending-audit",
                    f"Stamped {label}; audit recovery pending ({exc}). See docs/recovery.md.",
                    part_id,
                    output.removed_e,
                    output.changed_moves,
                )
    return Outcome(
        "stamped",
        f"Stamped {label} · {settings.layers} layers · {placed.height:g} mm · "
        f"{output.changed_moves} moves.",
        part_id,
        output.removed_e,
        output.changed_moves,
    )


def demo_data():
    from shapely.geometry import Point, box

    footprint = box(20, 20, 110, 80).buffer(5, quad_segs=12)
    footprint = footprint.difference(Point(33, 67).buffer(4)).difference(Point(97, 67).buffer(4))
    surface = footprint.buffer(-2)
    settings = Settings(counter_prefix="A")
    placed = auto_place(
        ">PETG< A042", surface, settings.text_height_mm, settings.min_text_height_mm
    )
    return footprint, surface, placed, settings
