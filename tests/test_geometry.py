from __future__ import annotations

import pytest
from shapely import affinity
from shapely.geometry import Point, box

from basemark.errors import SafeSkip
from basemark.placement import auto_place
from basemark.text_geom import text_polygons


def test_font_cap_height_mirror_and_holes():
    normal = text_polygons("PLA", 6, mirrored=False)
    mirrored = text_polygons("PLA", 6)
    assert normal.bounds[3] - normal.bounds[1] == pytest.approx(6)
    assert affinity.scale(mirrored, xfact=-1, yfact=1, origin=(0, 0)).equals_exact(normal, 1e-7)
    zero = text_polygons("0", 6)
    assert len(zero.interiors) == 1
    assert not zero.contains(zero.centroid)


def test_holes_and_concave_surface_respected():
    surface = box(0, 0, 100, 50).difference(Point(50, 25).buffer(10))
    placement = auto_place(">PETG< A042", surface, 6, 4)
    assert placement.fits(surface)
    assert not placement.geometry.envelope.intersects(Point(50, 25).buffer(10))


def test_auto_shrink():
    big = text_polygons(">PLA< 001", 6)
    width = (big.bounds[2] - big.bounds[0]) * 0.83
    placement = auto_place(">PLA< 001", box(0, 0, width, 15), 6, 4)
    assert 4 <= placement.height < 6


def test_tiny_surface_skipped():
    with pytest.raises(SafeSkip, match="does not fit"):
        auto_place(">PLA< 001", box(0, 0, 5, 5), 6, 4)


@pytest.mark.parametrize("text", ["", "\n", "🖨", "X" * 81])
def test_unsupported_text_is_explicit(text):
    with pytest.raises(SafeSkip):
        text_polygons(text, 6)
