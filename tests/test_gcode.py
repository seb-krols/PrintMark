from __future__ import annotations

import math
import random

import pytest
from conftest import coupon
from shapely.geometry import Point, box

from basemark.errors import SafeSkip
from basemark.footprint import layer_footprint, placement_surface
from basemark.gcode_parser import parse
from basemark.gcode_writer import rewrite
from basemark.placement import auto_place


def reparsed(output):
    # Duplicate-stamp protection is a service constraint, not an interpreter constraint.
    return parse(
        "\n".join(line for line in output.splitlines() if not line.startswith("; BASEMARK"))
    )


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("relative_xyz", [False, True])
def test_extrusion_conservation_and_coordinate_restore(absolute, relative_xyz):
    original = coupon(absolute=absolute, relative_xyz=relative_xyz)
    program = parse(original)
    label = box(30, 20, 40, 25).difference(box(33, 21, 37, 24))
    result = rewrite(program, label, 2, "A001")
    after = reparsed(result.text)
    assert sum(m.delta_e for m in program.moves) - sum(
        m.delta_e for m in after.moves
    ) == pytest.approx(result.removed_e, abs=1e-6)
    assert after.moves[-1].end == pytest.approx(program.moves[-1].end, abs=1e-6)
    if absolute:
        assert after.moves[-1].e_end == pytest.approx(program.moves[-1].e_end, abs=1e-7)
    assert [m.delta_e for m in after.moves if m.delta_e < 0] == pytest.approx(
        [m.delta_e for m in program.moves if m.delta_e < 0]
    )
    assert result.text.split(";LAYER_CHANGE")[3:] == original.split(";LAYER_CHANGE")[3:]
    assert result.text.endswith("; spiral_vase = 0\n")
    # E is filament length. Convert to volume before comparing with recess area.
    removed_volume = result.removed_e * math.pi * (1.75 / 2) ** 2
    assert removed_volume == pytest.approx(label.area * 2 * 0.2, rel=0.12)
    for move in after.moves:
        if move.part and move.layer < 2:
            midpoint = Point((move.start[0] + move.end[0]) / 2, (move.start[1] + move.end[1]) / 2)
            assert not label.buffer(-1e-5).contains(midpoint)


def test_purge_skirt_and_upper_layers_are_byte_identical(gcode):
    result = rewrite(parse(gcode), box(0, 0, 60, 25), 2, "001")
    for line in gcode.splitlines(keepends=True):
        if "untouched" in line:
            assert line in result.text
    assert result.text.split(";LAYER_CHANGE")[3:] == gcode.split(";LAYER_CHANGE")[3:]


def test_footprint_excludes_purge_skirt(gcode):
    footprint = layer_footprint(parse(gcode), 0)
    assert not footprint.covers(Point(1, 0))
    assert not footprint.covers(Point(7, 5))
    assert footprint.covers(Point(20, 20))


def test_crlf_preserved(gcode):
    source = gcode.replace("\n", "\r\n")
    result = rewrite(parse(source), box(30, 20, 40, 25), 2, "001")
    assert "\n" not in result.text.replace("\r\n", "")


@pytest.mark.parametrize(
    "command",
    [
        "G2 X40 Y30 I2 J0 E1",
        "G3 X40 Y30 R3 E1",
        "G20",
        "M200 D1.75",
        "G10",
        "M600",
        "G54",
        "T1",
        "G92 X0",
        "G1 XNaN E1",
        "G1 X20 X30 E1",
        "G1 X20 E1 Q2",
        "N20 G1 X20 E1*20",
        "G1 X20 E1e-3",
    ],
)
def test_unknown_motion_fails_closed(gcode, command):
    source = gcode.replace(";TYPE:Solid infill", f";TYPE:Solid infill\n{command}", 1)
    with pytest.raises(SafeSkip):
        parse(source)


def test_missing_e_mode_and_g90_invalidation(gcode):
    with pytest.raises(SafeSkip, match="E mode"):
        parse(gcode.replace("M83\n", ""))
    with pytest.raises(SafeSkip, match="E mode"):
        parse(gcode.replace("M83\n", "M83\nG90\n"))


def test_prusa_decimal_profile_checks_are_untouched(gcode):
    start = 'M862.3 P "MK3S"\nM862.1 P0.4\nM115 U3.14.0\n'
    source = start + gcode
    result = rewrite(parse(source), box(30, 20, 40, 25), 2, "001")
    assert start in result.text


def test_prusa_buddy_firmware_commands_are_untouched(gcode):
    # As emitted by PrusaSlicer's stock MK4(S)/MK3.9/MINI/XL/CORE One start and end G-code.
    start = "M555 X85 Y81 W80 H44\nM591 S0\nM141 S20\nM569 S0 E\nM572 S0.036\nM142 S36\n"
    source = start + gcode.replace(";TYPE:Solid infill", "M74 W0.78\n;TYPE:Solid infill", 1)
    end = "M141 S0\nM572 S0\nM593 X T2 F0\nM569 S1 X Y\n"
    source = source.replace("M84\n", end + "M84\n")
    result = rewrite(parse(source), box(30, 20, 40, 25), 2, "001")
    assert start in result.text
    assert "M74 W0.78\n" in result.text and end in result.text


def test_firmware_object_labels_name_objects(gcode):
    labels = "M486 S0\nM486 Abasemark coupon.stl\nM486 S-1\n"
    program = parse(labels + gcode.replace("; printing object coupon.stl id:0 copy 0\n", ""))
    assert program.objects == ["basemark coupon.stl"]


def test_empty_g92_is_ambiguous(gcode):
    with pytest.raises(SafeSkip, match="G92"):
        parse(gcode.replace("G92 E0", "G92"))


def test_unknown_startup_macro_is_not_assumed_harmless(gcode):
    with pytest.raises(SafeSkip, match="setup command M98"):
        parse("M98 Pmystery.g\n" + gcode)


def test_absolute_requires_e_origin():
    with pytest.raises(SafeSkip, match="G92"):
        parse(coupon(absolute=True).replace("G92 E0\n", ""))


def test_sequential_and_vase_fail_closed(gcode):
    with pytest.raises(SafeSkip, match="non-increasing"):
        parse(gcode.replace(";Z:0.4", ";Z:0.2"))
    with pytest.raises(SafeSkip, match="non-planar"):
        parse(gcode.replace("X90.000000 Y10.000000 Z0.200000", "X90 Y10 Z0.3", 1))


def test_requires_roof_and_solid_bottom(gcode):
    with pytest.raises(SafeSkip, match="roof"):
        placement_surface(parse(coupon(layers=2)), 2, 2)
    sparse = gcode.replace(";TYPE:Solid infill", ";TYPE:Internal infill")
    with pytest.raises(SafeSkip, match="solid"):
        placement_surface(parse(sparse), 2, 2)


def test_wipe_extrusions_are_protected(gcode):
    marker = "G1 X90.000000 Y20.000000 Z0.200000"
    line = next(line for line in gcode.splitlines() if line.startswith(marker))
    source = gcode.replace(line, ";WIPE_START\n" + line + "\n;WIPE_END", 1)
    result = rewrite(parse(source), box(30, 20, 40, 25), 2, "001")
    assert line in result.text


@pytest.mark.parametrize("seed", range(10))
def test_random_rectangles_conserve_e(seed):
    rng = random.Random(seed)
    original = coupon(absolute=bool(seed % 2), relative_xyz=bool(seed % 3))
    program = parse(original)
    label = box(rng.uniform(15, 25), rng.uniform(12, 20), rng.uniform(50, 85), rng.uniform(25, 40))
    result = rewrite(program, label, 2, f"R{seed}")
    after = reparsed(result.text)
    assert sum(m.delta_e for m in program.moves) - sum(
        m.delta_e for m in after.moves
    ) == pytest.approx(result.removed_e, abs=1e-5)
    assert after.moves[-1].end == pytest.approx(program.moves[-1].end, abs=1e-6)


def test_actual_text_can_be_placed_and_stamped(gcode):
    program = parse(gcode)
    _, surface = placement_surface(program, 2, 2)
    label = auto_place(">PLA< A001", surface, 6, 4)
    result = rewrite(program, label.geometry, 2, "A001")
    assert result.changed_moves > 10
    assert result.removed_e > 0


def test_memory_optimization_still_validates_entire_tail(gcode):
    limited = parse(gcode, retain_layers=3)
    assert max(move.layer for move in limited.moves) == 2
    assert limited.layers == 4
    with pytest.raises(SafeSkip, match="G2"):
        parse(gcode.replace("M84", "G2 X1 Y2 E1 I1 J0"), retain_layers=3)
