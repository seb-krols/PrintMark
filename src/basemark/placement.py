from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity, contains_xy
from shapely.geometry import Point, box
from shapely.ops import polylabel

from .errors import SafeSkip
from .footprint import polygons
from .text_geom import text_polygons


@dataclass(frozen=True)
class Placement:
    text: str
    height: float
    x: float
    y: float
    angle: float = 0.0

    @property
    def geometry(self):
        shape = text_polygons(self.text, self.height)
        shape = affinity.rotate(shape, self.angle, origin=(0, 0))
        return affinity.translate(shape, self.x, self.y)

    def fits(self, surface) -> bool:
        # The complete label rectangle must fit; do not weave letters around holes.
        return surface.covers(self.geometry.envelope)


def auto_place(text: str, surface, height: float, minimum: float) -> Placement:
    regions = sorted(polygons(surface), key=lambda p: p.area, reverse=True)[:8]
    candidates = []
    for region in regions:
        pole = polylabel(region, tolerance=0.3)
        candidates.extend([pole, region.centroid, region.representative_point()])
        left, bottom, right, top = region.bounds
        for iy in range(1, 16):
            for ix in range(1, 24):
                x = left + (right - left) * ix / 24
                y = bottom + (top - bottom) * iy / 16
                if contains_xy(region, x, y):
                    candidates.append(Point(x, y))
    sizes = [height]
    while sizes[-1] > minimum + 1e-6:
        sizes.append(max(minimum, round(sizes[-1] - 0.5, 6)))
    for size in sizes:
        shape = text_polygons(text, size)
        # Prefer readable full-size text. Try a quarter turn before shrinking;
        # retain the familiar horizontal layout whenever it fits at this size.
        for angle in (0, 90):
            left, bottom, right, top = affinity.rotate(shape, angle, origin=(0, 0)).bounds
            fits = []
            for point in candidates:
                rect = box(left + point.x, bottom + point.y, right + point.x, top + point.y)
                if surface.covers(rect):
                    fits.append((rect.distance(surface.boundary), point))
            if fits:
                _, best = max(fits, key=lambda item: item[0])
                return Placement(text, size, best.x, best.y, angle)
    raise SafeSkip("label does not fit the largest island at the minimum text height")
