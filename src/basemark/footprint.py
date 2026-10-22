from __future__ import annotations

from shapely import buffer, union_all
from shapely.geometry import LineString, Polygon

from .errors import SafeSkip
from .gcode_parser import SOLID_TYPES, Program


def layer_footprint(program: Program, layer: int, *, solid_only: bool = False):
    moves = [
        m
        for m in program.moves
        if m.layer == layer and m.part and (not solid_only or m.feature in SOLID_TYPES)
    ]
    if not moves:
        raise SafeSkip(f"no {'solid ' if solid_only else ''}part paths in layer {layer + 1}")
    paths = [LineString([m.start[:2], m.end[:2]]) for m in moves]
    # Vectorized GEOS work keeps large first layers practical. Do not fill holes or
    # use a convex hull: that could manufacture a false surface over empty space.
    result = union_all(buffer(paths, [m.width / 2 for m in moves], quad_segs=4))
    if result.is_empty or not result.is_valid:
        raise SafeSkip("could not reconstruct a valid deposited footprint")
    return result


def polygons(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from polygons(part)


def placement_surface(program: Program, layers: int, margin: float):
    if program.layers <= layers:
        raise SafeSkip("the part needs at least one solid roof layer above the stamp")
    footprint = layer_footprint(program, 0)
    islands = list(polygons(footprint))
    if not islands:
        raise SafeSkip("no first-layer island")
    largest = max(islands, key=lambda p: p.area)
    safe = largest.buffer(-margin)
    # Require deposited solid material through the recess AND the roof. This also
    # avoids putting a two-layer stamp through a thin tab or into sparse infill.
    for layer in range(layers + 1):
        solid = layer_footprint(program, layer, solid_only=True)
        safe = safe.intersection(solid)
    if safe.is_empty or safe.area < 4:
        raise SafeSkip("no solid surface through the stamp depth and its roof")
    return footprint, safe


def largest_polygon(geometry) -> Polygon:
    parts = list(polygons(geometry))
    if not parts:
        raise SafeSkip("no usable placement region")
    return max(parts, key=lambda p: p.area)
