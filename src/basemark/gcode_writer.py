from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from shapely import union_all
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge
from shapely.prepared import prep

from .errors import SafeSkip
from .footprint import polygons
from .gcode_parser import Move, Program

PERIMETERS = ("External perimeter", "Perimeter", "Overhang perimeter")
# Outline points closer than this to a straight line are dropped (G-code size).
SIMPLIFY_MM = 0.02
# Shorter travels are not worth a retraction (PrusaSlicer's own threshold is 1-2 mm).
RETRACT_MIN_MM = 1.0
# The slicer's lines reach this share of a line width into a wall, so they bond to it
# and leave no gaps along it (PrusaSlicer's own infill/perimeter overlap is 10-25%).
OVERLAP = 0.15


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
    removed_e: float  # net: plastic left out of the letters minus the outlines added
    changed_moves: int


@dataclass(frozen=True)
class Style:
    """How one stamped layer draws a wall, measured from the slicer's own moves."""

    width: float
    e_per_mm: float
    feed: float
    travel: float


@dataclass(frozen=True)
class Retract:
    length: float
    feed: float
    restore_feed: float


def styles(program: Program, layers: int):
    """Per-layer wall style, the feed rate in effect at each move, and the retraction."""
    feed = 0.0
    feeds: dict[int, float] = {}
    walls: dict[int, list] = {}
    fills: dict[int, list] = {}
    travels: dict[int, float] = {}
    retract, pending = None, None
    for move in program.moves:
        feed = move.params.get("F", feed)
        feeds[move.index] = feed
        planar = move.length > 1e-9
        if not planar and move.layer >= 0 and retract is None:
            # A pure E move: the file's own retraction, then its matching unretraction.
            if move.delta_e < 0 and pending is None:
                pending = (-move.delta_e, feed)
            elif move.delta_e > 0 and pending is not None:
                retract = Retract(*pending, feed)
        if not 0 <= move.layer < layers:
            continue
        if move.part and move.length > 0.2:
            sample = (move.delta_e / move.length, move.width, feed)
            group = walls if move.feature in PERIMETERS else fills
            group.setdefault(move.layer, []).append(sample)
        elif planar and move.delta_e == 0:
            travels[move.layer] = max(travels.get(move.layer, 0.0), feed)
    result = {}
    for layer in range(layers):
        samples = walls.get(layer) or fills.get(layer)
        if not samples:
            continue
        speed = statistics.median(s[2] for s in samples) or 1200.0
        result[layer] = Style(
            statistics.median(s[1] for s in samples),
            statistics.median(s[0] for s in samples),
            speed,
            travels.get(layer) or max(speed, 3000.0),
        )
    return result, feeds, retract


def clip(move: Move, prepared, region):
    """The move without extrusion inside region: (G-code words, E taken, path), or None."""
    path = LineString([move.start[:2], move.end[:2]])
    if not prepared.intersects(path):
        return None
    cuts = [0.0, 1.0]
    cuts.extend(
        path.project(p, normalized=True) for p in points(path.intersection(region.boundary))
    )
    cuts = sorted(set(round(max(0.0, min(1.0, t)), 12) for t in cuts))
    intervals = [
        (a, b, prepared.covers(path.interpolate((a + b) / 2, normalized=True)))
        for a, b in zip(cuts, cuts[1:], strict=False)
        if b - a > 1e-10
    ]
    if not any(inside for _, _, inside in intervals):
        return None
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
        output.append(" ".join(words))
        prior = end
    return output, move.delta_e - kept, path


def lines_of(geometry):
    if geometry.geom_type == "LineString":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from lines_of(part)


def wall_paths(letters: list, width: float):
    """Per letter, its wall lines: (letter number, points, closed).

    A wall runs half a line width outside the letter, so the line's inner edge is the
    letter's edge and the letter stays empty. Where a neighbour is too close for two
    walls, or a counter (the hole in A, O, 8) is too small for one, there is no wall:
    that spot keeps the slicer's own lines, so nothing is printed twice."""
    paths = []
    for n, letter in enumerate(letters):
        others = letters[:n] + letters[n + 1 :]
        near = union_all(others).buffer(1.5 * width) if others else None
        for polygon in polygons(letter.buffer(width / 2, quad_segs=4)):
            for ring in (polygon.exterior, *polygon.interiors):
                ring = ring.simplify(SIMPLIFY_MM)
                if len(ring.coords) < 4 or Polygon(ring).area < width * width:
                    continue
                line = LineString(ring.coords)
                if near is None or not line.intersects(near):
                    paths.append((n, list(ring.coords)[:-1], True))
                    continue
                for piece in lines_of(linemerge(list(lines_of(line.difference(near))))):
                    if piece.length >= width:
                        paths.append((n, list(piece.coords), False))
    return paths


def cleared(label, paths, width: float):
    """Where the slicer's lines are taken out: the letters, and each wall's strip from
    the letter edge out to the wall's far side less the bonding overlap."""
    if not paths:
        return label
    lines = union_all([LineString(p + p[:1] if closed else p) for _, p, closed in paths])
    inner = lines.buffer(width / 2).intersection(label.buffer(width / 2))
    return union_all([label, inner, lines.buffer(width * (0.5 - OVERLAP))])


def walls(move: Move, loops, style: Style, retract: Retract | None, feed: float, nl: str):
    """G-code that draws the loops, starting and ending where move starts."""
    lines = [
        "; BaseMark letter outlines",
        ";TYPE:External perimeter",
        f";WIDTH:{fmt(style.width, 4)}",
    ]
    pos = move.start[:2]
    e = move.e_start
    added = 0.0

    def go(x, y, extrude=0.0, speed=None):
        nonlocal pos, e, added
        x, y = round(x, 7), round(y, 7)
        a, b = (x - pos[0], y - pos[1]) if move.xyz_relative else (x, y)
        words = ["G1", f"X{fmt(a)}", f"Y{fmt(b)}"]
        if extrude:
            e += extrude
            added += extrude
            words.append(f"E{fmt(extrude if move.e_relative else e, 9)}")
        if speed:
            words.append(f"F{fmt(speed)}")
        lines.append(" ".join(words))
        pos = (x, y)

    def pump(length, speed):
        nonlocal e
        e += length
        lines.append(f"G1 E{fmt(length if move.e_relative else e, 9)} F{fmt(speed)}")

    def travel(x, y):
        far = retract is not None and math.dist(pos, (x, y)) >= RETRACT_MIN_MM
        if far:
            pump(-retract.length, retract.feed)
        go(x, y, speed=style.travel)
        if far:
            pump(retract.length, retract.restore_feed)

    def entry(path):
        points, closed = path
        return min(math.dist(pos, p) for p in (points if closed else (points[0], points[-1])))

    remaining = list(loops)
    while remaining:
        # Nearest wall next, entered at its nearest point: short travels.
        path = min(remaining, key=entry)
        remaining.remove(path)
        points, closed = path
        if closed:
            start = min(range(len(points)), key=lambda i: math.dist(pos, points[i]))
            points = points[start:] + points[: start + 1]
        elif math.dist(pos, points[-1]) < math.dist(pos, points[0]):
            points = points[::-1]
        travel(*points[0])
        for n, point in enumerate(points[1:]):
            go(*point, math.dist(pos, point) * style.e_per_mm, style.feed if n == 0 else None)
    travel(*move.start[:2])
    if feed:
        lines.append(f"G1 F{fmt(feed)}")  # the original move may rely on the modal feed
    if not move.e_relative:
        lines.append(f"G92 E{fmt(move.e_start, 9)} ; BaseMark restore E coordinate")
    lines += [f";TYPE:{move.feature}", f";WIDTH:{fmt(move.width, 4)}"]
    return "".join(line + nl for line in lines), added


def rewrite(program: Program, label, layers: int, stamp_id: str) -> Rewrite:
    """Turn each letter into an empty pocket with its own wall around it.

    In the stamped layers no plastic goes into the letters or a band one line width
    around them; a wall loop then fills that band, drawn just before the infill like
    the part's own perimeters. The pocket keeps crisp edges that neighbouring lines
    cannot squash into, and the solid layer above bridges over it.
    """
    if label.is_empty or not label.is_valid:
        raise SafeSkip("invalid label geometry")
    style, feeds, retract = styles(program, layers)
    letters = list(polygons(label))
    paths = {layer: wall_paths(letters, s.width) for layer, s in style.items()}
    regions = {layer: cleared(label, paths[layer], s.width) for layer, s in style.items()}
    prepared = {layer: prep(region) for layer, region in regions.items()}
    changes: dict[int, list[str]] = {}
    hits: dict[int, list] = {}
    nl = program.newline
    removed, count = 0.0, 0
    for move in program.moves:
        if move.layer >= layers or not move.part or move.layer not in regions:
            continue
        cut = clip(move, prepared[move.layer], regions[move.layer])
        if cut is None:
            continue
        words, taken, path = cut
        text = ["".join(line + nl for line in words)]
        if not move.e_relative:
            # Restore the original logical E coordinate without moving the motor.
            # This keeps every subsequent original line byte-identical, including
            # retractions, mode changes, and the unmodified upper layers.
            text.append(f"G92 E{fmt(move.e_end, 9)} ; BaseMark restore E coordinate{nl}")
        changes[move.index] = text
        hits.setdefault(move.layer, []).append((move, path))
        removed += taken
        count += 1
    if not count or removed <= 0:
        raise SafeSkip("label does not intersect printable paths")
    added = 0.0
    for layer, cut_moves in hits.items():
        s = style[layer]
        # A letter's wall goes just before the first move cut for it: inside the same
        # object (M486 / cancel object) and ahead of that object's infill.
        targets = []
        for letter in letters:
            zone = letter.buffer(s.width)
            targets.append(next((m for m, p in cut_moves if zone.intersects(p)), cut_moves[0][0]))
        groups: dict[int, list] = {}
        for n, points, closed in paths[layer]:
            groups.setdefault(targets[n].index, []).append((points, closed))
        for index, loops in groups.items():
            move = targets[next(n for n, t in enumerate(targets) if t.index == index)]
            text, extra = walls(move, loops, s, retract, feeds.get(index, 0.0), nl)
            changes[index].insert(0, text)
            added += extra
    net = removed - added
    marker = f"; BASEMARK stamp {stamp_id}; layers={layers}; removed_filament_mm={fmt(net)}{nl}"
    result = marker + "".join(
        "".join(changes[i]) if i in changes else line for i, line in enumerate(program.lines)
    )
    return Rewrite(result, net, count)
