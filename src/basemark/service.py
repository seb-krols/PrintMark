from __future__ import annotations

import socket
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shapely import union_all

from .config import Settings, atomic_write, load_settings, validate_paths
from .counter import Counter, digest
from .env import job_from, metadata
from .errors import SafeSkip
from .footprint import Part, plate_parts
from .gcode_parser import parse
from .gcode_writer import rewrite
from .placement import Placement, auto_place
from .preview import svg_preview


@dataclass(frozen=True)
class Outcome:
    status: str
    message: str
    part_id: str = ""
    removed_e: float = 0
    changed_moves: int = 0


@dataclass(frozen=True)
class Plate:
    """Everything the export window shows: the whole first layer and its parts."""

    footprint: object
    parts: list[Part]
    job_name: str = ""


@dataclass(frozen=True)
class Stamps:
    """The labels chosen for one export, one per stamped part."""

    placements: list[Placement]
    total: int  # parts on the plate, stamped or not

    @property
    def geometry(self):
        return union_all([p.geometry for p in self.placements])

    @property
    def height(self) -> float:
        return min(p.height for p in self.placements)

    @property
    def count(self) -> str:
        """'3 of 4 parts · ' on a plate of several parts; nothing for a single part."""
        stamped = len(self.placements)
        if self.total == 1:
            return ""
        if stamped < self.total:
            return f"{stamped} of {self.total} parts · "
        return f"{stamped} parts · "

    def summary(self, label: str, settings: Settings, moves: int) -> str:
        sizes = sorted({p.height for p in self.placements})
        size = f"{sizes[0]:g} mm" if len(sizes) == 1 else f"{sizes[0]:g}–{sizes[-1]:g} mm"
        return f"Stamped {label} · {self.count}{settings.layers} layers · {size} · {moves} moves."

    def svg(self, plate: Plate) -> str:
        surface = union_all([part.surface for part in plate.parts])
        return svg_preview(plate.footprint, surface, self.placements)


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
    footprint, parts = plate_parts(
        program, settings.layers, settings.margin_mm, every_part=settings.every_part
    )
    validate_paths(config, settings, path, preview)
    plate = Plate(footprint, parts, Path(job.output_name or path).name)
    if not settings.numbered:
        return stamp_material_only(
            path, original, job, program, plate, settings, dry_run, preview, choose
        )
    counter_path, log_path = settings.paths(config.parent)
    with Counter(counter_path, settings.counter_next, recover=not dry_run) as counter:
        if counter.state.get("pending"):
            raise SafeSkip("counter recovery is pending; open Settings → Diagnostics to recover")
        # One number per export: every part on the plate carries it, and the log
        # entry lists the plate's objects.
        part_id = settings.counter_prefix + str(counter.next).zfill(settings.counter_digits)
        now = datetime.now(UTC)
        label = settings.template.format(
            material=job.material,
            id=part_id,
            prefix=settings.counter_prefix,
            date=now.date().isoformat(),
        )
        stamps = place_labels(plate, label, settings, job.material, part_id, dry_run, choose)
        if stamps is None:
            return user_skip()
        output = rewrite(program, stamps.geometry, settings.layers, part_id)
        with counter.guard_id(log_path, part_id):
            if preview:
                atomic_write(preview, stamps.svg(plate).encode("utf-8"))
            if dry_run:
                return Outcome(
                    "preview",
                    f"Preview {label}: {stamps.count}{output.changed_moves} moves; no ID consumed.",
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
                "text_height_mm": stamps.height,
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
        stamps.summary(label, settings, output.changed_moves),
        part_id,
        output.removed_e,
        output.changed_moves,
    )


def auto_labels(parts: list[Part], label: str, settings: Settings) -> list[Placement | None]:
    """Automatic placement on each part; None where the label does not fit."""
    result = []
    for part in parts:
        placed = None
        if part.usable:
            try:
                placed = auto_place(
                    label, part.surface, settings.text_height_mm, settings.min_text_height_mm
                )
            except SafeSkip:
                pass
        result.append(placed)
    return result


def place_labels(plate, label, settings, material, part_id, dry_run, choose) -> Stamps | None:
    """A label on every part it fits; the operator may adjust them. None = skipped."""
    placements = auto_labels(plate.parts, label, settings)
    if not any(placements):
        where = "the part" if len(plate.parts) == 1 else "any part"
        raise SafeSkip(f"label does not fit {where} at the minimum text height")
    if settings.mode == "interactive" and not dry_run:
        if choose is None:
            from .popup import choose_placement

            choose = choose_placement
        placements = choose(plate, placements, settings, material, part_id)
        if placements is None:
            return None
    chosen = []
    for part, placed in zip(plate.parts, placements, strict=True):
        if placed is None:
            continue
        if not placed.fits(part.surface):
            raise SafeSkip("placement is outside the solid surface or margin")
        chosen.append(placed)
    if not chosen:
        return None  # the operator switched every part off
    return Stamps(chosen, len(plate.parts))


def user_skip() -> Outcome:
    from .notify import USER_SKIP

    return Outcome("skipped", USER_SKIP)


def stamp_material_only(
    path, original, job, program, plate, settings, dry_run, preview, choose
) -> Outcome:
    """A label without a part number: no ID is used, so there is no counter or log entry."""
    label = settings.template.format(
        material=job.material,
        id="",
        prefix=settings.counter_prefix,
        date=datetime.now(UTC).date().isoformat(),
    ).strip()
    stamps = place_labels(plate, label, settings, job.material, "", dry_run, choose)
    if stamps is None:
        return user_skip()
    output = rewrite(program, stamps.geometry, settings.layers, label)
    if preview:
        atomic_write(preview, stamps.svg(plate).encode("utf-8"))
    if dry_run:
        return Outcome(
            "preview",
            f"Preview {label}: {stamps.count}{output.changed_moves} moves.",
            "",
            output.removed_e,
            output.changed_moves,
        )
    if path.read_bytes() != original:
        raise SafeSkip("G-code changed during placement; export again")
    atomic_write(path, output.text.encode("utf-8"), mode=stat.S_IMODE(path.stat().st_mode))
    return Outcome(
        "stamped",
        stamps.summary(label, settings, output.changed_moves),
        "",
        output.removed_e,
        output.changed_moves,
    )


def demo_data(material: str = "PETG"):
    """A plate of two parts for the demo and UI tests: a bracket and a small tag."""
    from shapely.geometry import Point, box

    bracket = box(20, 20, 110, 80).buffer(5, quad_segs=12)
    bracket = bracket.difference(Point(33, 67).buffer(4)).difference(Point(97, 67).buffer(4))
    tag = box(128, 22, 146, 34).buffer(2, quad_segs=8)
    settings = Settings()
    parts = [
        Part("bracket.stl", bracket, bracket.buffer(-settings.margin_mm)),
        Part("tag.stl", tag, tag.buffer(-settings.margin_mm)),
    ]
    plate = Plate(union_all([bracket, tag]), parts, "bracket_and_tag_0.2mm_PETG_MK4IS.gcode")
    return plate, auto_labels(parts, material, settings), settings
