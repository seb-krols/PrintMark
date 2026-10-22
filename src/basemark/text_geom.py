from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely import affinity, union_all
from shapely.geometry import Polygon

from .errors import SafeSkip

FONT_PATH = Path(__file__).parent / "assets" / "Lato-Bold.ttf"


class FlattenPen(BasePen):
    """Flatten TrueType/CFF outlines to a bounded geometric tolerance."""

    def __init__(self, glyph_set, tolerance=1.0):
        super().__init__(glyph_set)
        self.tolerance = tolerance
        self.contours = []
        self.points = []

    def _moveTo(self, point):
        self.points = [point]

    def _lineTo(self, point):
        self.points.append(point)

    def _curveToOne(self, p1, p2, p3):
        self._flatten([self._getCurrentPoint(), p1, p2, p3])

    def _qCurveToOne(self, p1, p2):
        self._flatten([self._getCurrentPoint(), p1, p2])

    def _flatten(self, points, depth=0):
        # Distance to the chord bounds the flatness of the Bezier control polygon.
        a, b = points[0], points[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5
        distance = max(
            (
                abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / length
                if length
                else ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
            )
            for p in points[1:-1]
        )
        if distance <= self.tolerance or depth >= 16:
            self.points.append(b)
            return
        levels = [points]
        while len(levels[-1]) > 1:
            row = levels[-1]
            levels.append(
                [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for p, q in zip(row, row[1:], strict=False)]
            )
        self._flatten([row[0] for row in levels], depth + 1)
        self._flatten([row[-1] for row in reversed(levels)], depth + 1)

    def _closePath(self):
        if len(self.points) >= 3:
            self.contours.append(self.points)
        self.points = []

    def _endPath(self):
        self._closePath()


@lru_cache(maxsize=128)
def text_polygons(text: str, height: float, mirrored: bool = True):
    if not text or len(text) > 80 or any(ord(c) < 32 or ord(c) > 126 for c in text):
        raise SafeSkip("label must contain 1–80 printable ASCII characters")
    with TTFont(FONT_PATH) as font:
        glyphs = font.getGlyphSet()
        cmap = font.getBestCmap()
        cap_height = font["OS/2"].sCapHeight
        scale = height / cap_height
        advance = 0.0
        letters = []
        for char in text:
            name = cmap.get(ord(char))
            if name is None:
                raise SafeSkip(f"font does not contain {char!r}")
            pen = FlattenPen(glyphs, tolerance=0.008 / scale)
            glyphs[name].draw(pen)
            # Bundled Lato has non-overlapping nested contours. Even/odd fill
            # preserves the counters in A, B, P, 0, etc.
            glyph = Polygon()
            for contour in pen.contours:
                ring = Polygon(contour)
                if not ring.is_valid:
                    raise SafeSkip("font outline is invalid")
                glyph = glyph.symmetric_difference(ring)
            if not glyph.is_empty:
                letters.append(affinity.translate(glyph, xoff=advance))
            advance += font["hmtx"][name][0]
    if not letters:
        raise SafeSkip("label contains no printable outlines")
    result = affinity.scale(union_all(letters), xfact=scale, yfact=scale, origin=(0, 0))
    if mirrored:
        result = affinity.scale(result, xfact=-1, yfact=1, origin=(0, 0))
    left, bottom, right, top = result.bounds
    return affinity.translate(result, xoff=-(left + right) / 2, yoff=-(bottom + top) / 2)
