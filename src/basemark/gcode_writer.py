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
# Lines must not simply pause across a letter: melted plastic keeps flowing for far
# longer than the ~60 ms a crossing takes, so it drags a strand over and fills the letter.
# They are rejoined around the letters instead, the way a slicer fills around a hole.
# A jump this long gets a retraction even off the letters (PrusaSlicer's own is 1-2 mm).
JUMP_MM = 2.0
# Up to this many moves apart, two cut moves are rejoined together.
BLOCK_GAP = 8
# A Bowden printer's full retraction is not needed for these short jumps.
MAX_RETRACT_MM = 2.0
RETRACTION = "; BaseMark retract"
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


FALLBACK_RETRACT = Retract(0.8, 2100.0, 1500.0)  # the file showed none to copy


def styles(program: Program, layers: int):
    """Per-layer wall style, the feed rate in effect at each move, and the retraction."""
    feed = 0.0
    feeds: dict[int, float] = {}
    walls: dict[int, list] = {}
    fills: dict[int, list] = {}
    travels: dict[int, float] = {}
    retract, retract_feed = None, None
    for move in program.moves:
        feed = move.params.get("F", feed)
        feeds[move.index] = feed
        planar = move.length > 1e-9
        if not planar and move.layer >= 0 and retract is None:
            # The file's own retraction. The length comes from the unretraction: with
            # wipe on, most of the retraction happens during the wipe's moves.
            if move.delta_e < 0:
                retract_feed = retract_feed or feed
            elif move.delta_e > 0:
                retract = Retract(min(move.delta_e, MAX_RETRACT_MM), retract_feed or feed, feed)
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
    return result, feeds, retract or FALLBACK_RETRACT


def spans(path: LineString, prepared, region, scrap: float):
    """Stretches of path as (from, to, inside region), as fractions of its length, or None.

    A stretch outside region but shorter than scrap, between two inside it, counts as
    inside: a dab of plastic that short has nothing to bond to and only blobs."""
    if not prepared.intersects(path):
        return None
    cuts = [0.0, 1.0]
    cuts.extend(
        path.project(p, normalized=True) for p in points(path.intersection(region.boundary))
    )
    cuts = sorted(set(round(max(0.0, min(1.0, t)), 12) for t in cuts))
    raw = [
        (a, b, prepared.covers(path.interpolate((a + b) / 2, normalized=True)))
        for a, b in zip(cuts, cuts[1:], strict=False)
        if b - a > 1e-10
    ]
    if not any(inside for _, _, inside in raw):
        return None
    result: list[tuple[float, float, bool]] = []
    for n, (a, b, inside) in enumerate(raw):
        inside = inside or (0 < n < len(raw) - 1 and (b - a) * path.length < scrap)
        if result and result[-1][2] == inside:
            result[-1] = (result[-1][0], b, inside)
        else:
            result.append((a, b, inside))
    return result


class Pen:
    """Writes moves from where the nozzle is, in the file's E and XYZ modes."""

    def __init__(self, move: Move, retract: Retract, travel: float, void):
        self.move = move
        self.retract = retract
        self.travel = travel
        self.void = void
        self.pos = move.start[:2]
        self.e = move.e_start
        self.feed = 0.0
        self.lines: list[str] = []

    def go(self, x, y, extrude=0.0, feed=0.0, comment=""):
        x, y = round(x, 7), round(y, 7)
        relative = self.move.xyz_relative
        a, b = (x - self.pos[0], y - self.pos[1]) if relative else (x, y)
        words = ["G1", f"X{fmt(a)}", f"Y{fmt(b)}"]
        if extrude:
            self.e += extrude
            words.append(f"E{fmt(extrude if self.move.e_relative else self.e, 9)}")
        if feed and feed != self.feed:
            words.append(f"F{fmt(feed)}")
            self.feed = feed
        if comment:
            words.append(f";{comment}")
        self.lines.append(" ".join(words))
        self.pos = (x, y)

    def pump(self, length: float, speed: float):
        """Move the filament without changing the file's E coordinate."""
        relative = self.move.e_relative
        word = length if relative else self.e + length
        self.lines.append(f"G1 E{fmt(word, 9)} F{fmt(speed)} {RETRACTION}")
        if not relative:
            self.lines.append(f"G92 E{fmt(self.e, 9)}")
        self.feed = speed

    def jump(self, x, y):
        """Go to (x, y) without printing, retracted if it is far or crosses a letter."""
        distance = math.dist(self.pos, (x, y))
        if distance < 1e-6:
            return
        dry = distance >= JUMP_MM or self.void.intersects(LineString([self.pos, (x, y)]))
        if dry:
            self.pump(-self.retract.length, self.retract.feed)
        self.go(x, y, feed=self.travel)
        if dry:
            self.pump(self.retract.length, self.retract.restore_feed)

    def finish(self, feed: float, e: float):
        """Leave the feed rate and E coordinate as the file's next lines expect."""
        if feed and feed != self.feed:
            self.lines.append(f"G1 F{fmt(feed)}")
        if not self.move.e_relative:
            self.lines.append(f"G92 E{fmt(e, 9)} ; BaseMark restore E coordinate")


@dataclass(frozen=True)
class Piece:
    """A stretch of a slicer line that is kept."""

    start: tuple[float, float]
    end: tuple[float, float]
    e: float
    feed: float
    comment: str

    def flipped(self) -> Piece:
        return Piece(self.end, self.start, self.e, self.feed, self.comment)


def joins(moves: list[Move], a: int, b: int) -> bool:
    """Can the moves from cut move a up to cut move b be printed in another order?

    Only lines of one kind in one object, with nothing retracted when they print."""
    first = moves[a]
    if b - a > BLOCK_GAP:
        return False
    kind = (first.layer, first.feature, first.obj, first.width)
    balance = 0.0
    for move in moves[a + 1 : b + 1]:
        if move.part:
            if (move.layer, move.feature, move.obj, move.width) != kind or abs(balance) > 1e-3:
                return False
        elif move.deposits:
            return False
        else:
            balance += move.delta_e
    return True


def blocks(moves: list[Move], cuts: dict) -> list[list[int]]:
    """Runs of cut moves to rejoin, as [first, last] positions in moves."""
    result: list[list[int]] = []
    for position in sorted(cuts):
        if result and joins(moves, result[-1][1], position):
            result[-1][1] = position
        else:
            result.append([position, position])
    return result


def unbroken(moves: list[Move], cuts: dict, feeds: dict) -> list[list[Piece]]:
    """The plastic of a run of moves as unbroken lines."""
    lines: list[list[Piece]] = []
    for move in moves:
        if not move.part:
            continue
        stretches = cuts[move.index][1] if move.index in cuts else [(0.0, 1.0, False)]
        comment = move.comment
        for a, b, inside in stretches:
            if inside:
                continue
            (x0, y0), (x1, y1) = move.start[:2], move.end[:2]
            start = (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a)
            end = (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)
            piece = Piece(start, end, move.delta_e * (b - a), feeds[move.index], comment)
            comment = ""
            if lines and math.dist(lines[-1][-1].end, start) < 1e-6:
                lines[-1].append(piece)
            else:
                lines.append([piece])
    return lines


def ordered(lines: list[list[Piece]], start, void) -> list[list[Piece]]:
    """The lines in print order: always the nearest free end that needs no letter crossed."""
    remaining = list(lines)
    result = []
    pos = start
    while remaining:
        ends = sorted(
            (math.dist(pos, point), n, flip, point)
            for n, line in enumerate(remaining)
            for flip, point in ((False, line[0].start), (True, line[-1].end))
        )
        chosen = next(
            (
                end
                for end in ends
                if end[0] < 1e-9 or not void.intersects(LineString([pos, end[3]]))
            ),
            ends[0],
        )
        _, n, flip, _ = chosen
        line = remaining.pop(n)
        line = [piece.flipped() for piece in reversed(line)] if flip else line
        result.append(line)
        pos = line[-1].end
    return result


def route(moves: list[Move], cuts, feeds, retract, travel, void):
    """Moves rewritten with their lines rejoined around the letters: (lines, E taken).

    moves is one block, by program index in cuts and feeds; it starts and ends on a cut
    print move, so the file's next line finds the nozzle where and as it expects."""
    head, tail = moves[0], moves[-1]
    pen = Pen(head, retract, travel, void)
    for line in ordered(unbroken(moves, cuts, feeds), head.start[:2], void):
        pen.jump(*line[0].start)
        for piece in line:
            pen.go(*piece.end, piece.e, piece.feed, piece.comment)
    pen.jump(*tail.end[:2])
    kept = pen.e - head.e_start
    pen.finish(feeds.get(tail.index, 0.0), tail.e_end)
    return pen.lines, sum(m.delta_e for m in moves) - kept


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
    walls, or a hole in the label is too small for one, there is no wall: that spot
    keeps the slicer's own lines, so nothing is printed twice."""
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


def walls(move: Move, loops, style: Style, retract: Retract, void, feed: float, nl: str):
    """G-code that draws the loops, starting and ending where move starts."""
    pen = Pen(move, retract, style.travel, void)

    def entry(path):
        points, closed = path
        ends = points if closed else (points[0], points[-1])
        return min(math.dist(pen.pos, p) for p in ends)

    remaining = list(loops)
    while remaining:
        # Nearest wall next, entered at its nearest point: short travels.
        path = min(remaining, key=entry)
        remaining.remove(path)
        points, closed = path
        if closed:
            start = min(range(len(points)), key=lambda i: math.dist(pen.pos, points[i]))
            points = points[start:] + points[: start + 1]
        elif math.dist(pen.pos, points[-1]) < math.dist(pen.pos, points[0]):
            points = points[::-1]
        pen.jump(*points[0])
        for point in points[1:]:
            pen.go(*point, math.dist(pen.pos, point) * style.e_per_mm, style.feed)
    pen.jump(*move.start[:2])
    added = pen.e - move.e_start
    pen.finish(feed, move.e_start)
    lines = [
        "; BaseMark letter outlines",
        ";TYPE:External perimeter",
        f";WIDTH:{fmt(style.width, 4)}",
        *pen.lines,
        f";TYPE:{move.feature}",
        f";WIDTH:{fmt(move.width, 4)}",
    ]
    return "".join(line + nl for line in lines), added


def rewrite(program: Program, label, layers: int, stamp_id: str) -> Rewrite:
    """Turn each letter into a cutout with its own wall around it.

    In the stamped layers no plastic goes into the letters or a band one line width
    around them; a wall loop then fills that band, drawn just before the infill like
    the part's own perimeters. The slicer's lines are cut there and rejoined around the
    letters, as if the model had the letters as holes, so the nozzle does not cross them.
    The solid layer above bridges over the letters.
    """
    if label.is_empty or not label.is_valid:
        raise SafeSkip("invalid label geometry")
    style, feeds, retract = styles(program, layers)
    letters = list(polygons(label))
    paths = {layer: wall_paths(letters, s.width) for layer, s in style.items()}
    regions = {layer: cleared(label, paths[layer], s.width) for layer, s in style.items()}
    prepared = {layer: prep(region) for layer, region in regions.items()}
    void = prep(label)
    moves = program.moves
    cuts: dict[int, tuple] = {}  # position in moves -> (path, stretches)
    travels = []  # the slicer's own unretracted travels over a letter
    primed = True
    for position, move in enumerate(moves):
        if move.delta_e:
            primed = move.delta_e > 0
        if move.layer not in regions or move.length <= 1e-9:
            continue
        path = LineString([move.start[:2], move.end[:2]])
        if move.part:
            found = spans(path, prepared[move.layer], regions[move.layer], style[move.layer].width)
            if found:
                cuts[position] = (path, found)
        elif (
            primed
            and not move.delta_e
            and abs(move.end[2] - move.start[2]) < 1e-9
            and void.intersects(path)
        ):
            travels.append(position)
    changes: dict[int, list[str]] = {}
    hits: dict[int, list] = {}
    nl = program.newline
    removed = 0.0
    rejoined = set()
    by_index = {moves[position].index: found for position, found in cuts.items()}
    for first, last in blocks(moves, cuts):
        block = moves[first : last + 1]
        rejoined.update(range(first, last + 1))
        travel = style[block[0].layer].travel
        lines, taken = route(block, by_index, feeds, retract, travel, void)
        removed += taken
        for move in block:
            changes[move.index] = []
        changes[block[0].index] = ["".join(line + nl for line in lines)]
        for position in range(first, last + 1):
            if position in cuts:
                hits.setdefault(block[0].layer, []).append((block[0], cuts[position][0]))
    if not cuts or removed <= 0:
        raise SafeSkip("label does not intersect printable paths")
    for position in travels:
        if position not in rejoined:
            move = moves[position]
            pen = Pen(move, retract, style[move.layer].travel, void)
            pen.jump(*move.end[:2])
            pen.finish(feeds.get(move.index, 0.0), move.e_end)
            changes[move.index] = ["".join(line + nl for line in pen.lines)]
    added = 0.0
    for layer, cut_moves in hits.items():
        s = style[layer]
        # A letter's wall goes just before the first block cut for it: inside the same
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
            text, extra = walls(move, loops, s, retract, void, feeds.get(index, 0.0), nl)
            changes[index].insert(0, text)
            added += extra
    net = removed - added
    marker = f"; BASEMARK stamp {stamp_id}; layers={layers}; removed_filament_mm={fmt(net)}{nl}"
    result = marker + "".join(
        "".join(changes[i]) if i in changes else line for i, line in enumerate(program.lines)
    )
    return Rewrite(result, net, len(cuts))
