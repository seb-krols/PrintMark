from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Point
from shapely.prepared import prep

from .errors import SafeSkip
from .gcode_parser import Program


def fmt(value: float, digits: int = 7) -> str:
    result = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if result in {"", "-0"} else result


def points(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Point":
        yield geometry
    elif geometry.geom_type in ("LineString", "LinearRing"):
        yield Point(geometry.coords[0])
        yield Point(geometry.coords[-1])
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from points(part)


@dataclass(frozen=True)
class Rewrite:
    text: str
    removed_e: float
    changed_moves: int


def rewrite(program: Program, label, layers: int, stamp_id: str) -> Rewrite:
    if label.is_empty or not label.is_valid:
        raise SafeSkip("invalid label geometry")
    prepared = prep(label)
    changes = {}
    removed, count = 0.0, 0
    nl = program.newline
    for move in program.moves:
        if move.layer >= layers or not move.part:
            continue
        path = LineString([move.start[:2], move.end[:2]])
        if not prepared.intersects(path):
            continue
        cuts = [0.0, 1.0]
        cuts.extend(
            path.project(p, normalized=True) for p in points(path.intersection(label.boundary))
        )
        cuts = sorted(set(round(max(0.0, min(1.0, t)), 12) for t in cuts))
        intervals = [
            (a, b, prepared.covers(path.interpolate((a + b) / 2, normalized=True)))
            for a, b in zip(cuts, cuts[1:], strict=False)
            if b - a > 1e-10
        ]
        if not any(inside for _, _, inside in intervals):
            continue
        output = []
        kept = 0.0
        prior = move.start[:2]
        for n, (a, b, inside) in enumerate(intervals):
            endpoint = path.interpolate(b, normalized=True)
            end = (round(endpoint.x, 7), round(endpoint.y, 7))
            x, y = end
            if move.xyz_relative:
                x, y = end[0] - prior[0], end[1] - prior[1]
            words = [move.command, f"X{fmt(x)}", f"Y{fmt(y)}"]
            if "Z" in move.params and n == 0:
                words.append(f"Z{fmt(move.params['Z'])}")
            if not inside:
                delta = move.delta_e * (b - a)
                kept += delta
                words.append(f"E{fmt(delta if move.e_relative else move.e_start + kept, 9)}")
            if "F" in move.params and n == 0:
                words.append(f"F{fmt(move.params['F'])}")
            if n == 0 and move.comment:
                words.append(f";{move.comment}")
            output.append(" ".join(words) + nl)
            prior = end
        if not move.e_relative:
            # Restore the original logical E coordinate without moving the motor.
            # This keeps every subsequent original line byte-identical, including
            # retractions, mode changes, and the unmodified upper layers.
            output.append(f"G92 E{fmt(move.e_end, 9)} ; BaseMark restore E coordinate{nl}")
        changes[move.index] = "".join(output)
        removed += move.delta_e - kept
        count += 1
    if not count or removed <= 0:
        raise SafeSkip("label does not intersect printable paths")
    marker = f"; BASEMARK stamp {stamp_id}; layers={layers}; removed_filament_mm={fmt(removed)}{nl}"
    result = marker + "".join(changes.get(i, line) for i, line in enumerate(program.lines))
    return Rewrite(result, removed, count)
