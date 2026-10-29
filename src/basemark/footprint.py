from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PureWindowsPath

from shapely import buffer, union_all
from shapely.geometry import LineString, Polygon

from .errors import SafeSkip
from .gcode_parser import SOLID_TYPES, Program

MIN_SURFACE = 4  # mm²; smaller safe areas cannot hold any letter


def layer_footprint(program: Program, layer: int, *, solid_only: bool = False):
    moves = [
        m
        for m in program.moves
        if m.layer == layer and m.part and (not solid_only or m.feature in SOLID_TYPES)
    ]
    if not moves:
        raise SafeSkip(f"no {'solid ' if solid_only else ''}part paths in layer {layer + 1}")
    return deposited(moves)


def deposited(moves):
    """The area covered by these extrusions (their paths widened to the bead width)."""
    # Join moves that continue each other into one polyline: GEOS widens a polyline far
    # faster than it merges thousands of separate segments (a full plate: 3x faster).
    runs, points, width = [], [], None
    for m in moves:
        if points and m.width == width and m.start[:2] == points[-1]:
            points.append(m.end[:2])
        else:
            if points:
                runs.append((points, width))
            points, width = [m.start[:2], m.end[:2]], m.width
    runs.append((points, width))
    paths = [LineString(run) for run, _ in runs]
    # Vectorized GEOS work keeps large first layers practical. Do not fill holes or
    # use a convex hull: that could manufacture a false surface over empty space.
    result = union_all(buffer(paths, [w / 2 for _, w in runs], quad_segs=4))
    if result.is_empty or not result.is_valid:
        raise SafeSkip("could not reconstruct a valid deposited footprint")
    return result


def polygons(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from polygons(part)


@dataclass(frozen=True)
class Part:
    """One part on the plate: its first-layer outline and where a label may go."""

    name: str
    outline: Polygon
    surface: object  # eroded solid area; may be empty when the part is too small

    @property
    def usable(self) -> bool:
        return not self.surface.is_empty and self.surface.area >= MIN_SURFACE


def display_name(name: str) -> str:
    """'models/clip.stl id:0 copy 1' -> 'clip.stl #2' for the export window."""
    match = re.fullmatch(r"(.*) id:\d+ copy (\d+)", name)
    if match:
        return f"{PureWindowsPath(match[1]).name} #{int(match[2]) + 1}"
    return PureWindowsPath(name).name or name


def plate_parts(program: Program, layers: int, margin: float, *, every_part: bool = True):
    """The plate's first-layer footprint and its parts, in print order.

    Labelled objects (PrusaSlicer's "Label objects" option, on in Prusa's own printer
    profiles) are one part each, stamped on their largest island. Without labels each
    separate first-layer island counts as a part. every_part=False keeps the largest only.
    """
    if program.layers <= layers:
        raise SafeSkip("the part needs at least one solid roof layer above the stamp")
    footprint = layer_footprint(program, 0)
    if not list(polygons(footprint)):
        raise SafeSkip("no first-layer island")
    # Require deposited solid material through the recess AND the roof. This also
    # avoids putting a two-layer stamp through a thin tab or into sparse infill.
    solid = footprint
    for layer in range(layers + 1):
        solid = solid.intersection(layer_footprint(program, layer, solid_only=True))
    groups: dict[str, list] = {}
    for move in program.moves:
        if move.layer == 0 and move.part:
            groups.setdefault(move.obj, []).append(move)
    if list(groups) == [""]:
        islands = sorted(
            polygons(footprint), key=lambda p: (-round(p.centroid.y / 10), p.centroid.x)
        )
        outlines = [(f"Part {n}", island) for n, island in enumerate(islands, start=1)]
    else:
        outlines = [
            (
                display_name(key) if key else "Unlabelled paths",
                largest_polygon(deposited(moves)),
            )
            for key, moves in groups.items()
        ]
    parts = [
        Part(name, outline, outline.buffer(-margin).intersection(solid))
        for name, outline in outlines
    ]
    if not every_part:
        parts = [max(parts, key=lambda p: p.outline.area)]
    if not any(part.usable for part in parts):
        raise SafeSkip("no solid surface through the stamp depth and its roof")
    return footprint, parts


def placement_surface(program: Program, layers: int, margin: float):
    """Footprint and label area of the largest part (the single-stamp behaviour)."""
    footprint, parts = plate_parts(program, layers, margin, every_part=False)
    return footprint, parts[0].surface


def largest_polygon(geometry) -> Polygon:
    parts = list(polygons(geometry))
    if not parts:
        raise SafeSkip("no usable placement region")
    return max(parts, key=lambda p: p.area)
