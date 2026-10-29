"""Several parts on one plate: one label per part."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import plate

from basemark.config import NUMBERED
from basemark.errors import SafeSkip
from basemark.footprint import display_name, plate_parts
from basemark.gcode_parser import parse
from basemark.service import process

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("labels", ["octoprint", "firmware", None])
def test_every_part_is_found(labels):
    _, parts = plate_parts(parse(plate(labels=labels)), 2, 1.5)
    assert len(parts) == 3
    assert all(part.usable for part in parts)
    expected = {
        "octoprint": ["part1.stl #1", "part2.stl #1", "part3.stl #1"],
        "firmware": ["part1.stl", "part2.stl", "part3.stl"],
        None: ["Part 1", "Part 2", "Part 3"],
    }[labels]
    assert [part.name for part in parts] == expected
    lefts = [part.outline.bounds[0] for part in parts]
    assert lefts == sorted(lefts)  # print order matches the plate from left to right


def test_firmware_labels_name_each_object():
    program = parse(plate(labels="firmware"))
    assert {m.obj for m in program.moves if m.part} == {"part1.stl", "part2.stl", "part3.stl"}


def test_display_names():
    assert display_name("models/clip.stl id:0 copy 1") == "clip.stl #2"
    assert display_name("clip.stl (Instance 2)") == "clip.stl (Instance 2)"
    assert display_name("C:\\parts\\clip.stl") == "clip.stl"


def test_largest_part_only_when_switched_off():
    sizes = ((20, 10), (40, 14), (30, 12))
    _, parts = plate_parts(parse(plate(sizes)), 2, 1.5, every_part=False)
    assert len(parts) == 1
    assert parts[0].outline.bounds[2] - parts[0].outline.bounds[0] == pytest.approx(40.45, 0.01)


def test_each_part_gets_a_label(tmp_path):
    job = tmp_path / "plate.gcode"
    job.write_text(plate())
    result = process(job, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.status == "stamped"
    assert "· 3 parts ·" in result.message
    stamped = parse("\n".join(job.read_text().splitlines()[1:]))
    original = parse(plate())
    for obj in {m.obj for m in original.moves if m.part}:

        def removed(program, obj=obj):
            return sum(m.delta_e for m in program.moves if m.obj == obj and m.layer < 2)

        assert removed(stamped) < removed(original) - 0.05, obj


def test_a_part_too_small_is_left_unstamped(tmp_path):
    job = tmp_path / "plate.gcode"
    job.write_text(plate(((30, 14), (5, 4), (30, 14))))
    result = process(job, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert "2 of 3 parts" in result.message


def test_nothing_fits_is_a_safe_skip(tmp_path):
    job = tmp_path / "plate.gcode"
    job.write_text(plate(((6, 5), (6, 5))))
    original = job.read_bytes()
    with pytest.raises(SafeSkip, match="any part"):
        process(job, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert job.read_bytes() == original


def test_operator_can_leave_parts_out(tmp_path):
    job = tmp_path / "plate.gcode"
    job.write_text(plate())

    def first_only(plate, placements, *args):
        return [placements[0], None, None]

    result = process(job, tmp_path / "config.toml", {}, {}, choose=first_only)
    assert "1 of 3 parts" in result.message
    job.write_text(plate())
    original = job.read_bytes()
    result = process(job, tmp_path / "config.toml", {}, {}, choose=lambda p, ps, *a: [None] * 3)
    assert result.status == "skipped"
    assert job.read_bytes() == original


def test_numbered_plate_uses_one_number(tmp_path):
    import csv

    job = tmp_path / "plate.gcode"
    job.write_text(plate(labels="firmware"))
    result = process(job, tmp_path / "config.toml", {"mode": "auto", "template": NUMBERED}, {})
    assert result.part_id == "001"
    rows = list(csv.DictReader((tmp_path / "log.csv").open()))
    assert len(rows) == 1
    assert rows[0]["object_names"] == "part1.stl | part2.stl | part3.stl"


def test_real_prusaslicer_plate_with_firmware_labels(tmp_path):
    source = FIXTURES / "prusaslicer-2.7.4-plate-firmware.gcode"
    _, parts = plate_parts(parse(source.read_text()), 2, 1.5)
    assert [part.name for part in parts] == [
        f"basemark-coupon.stl (Instance {n})" for n in (1, 2, 3)
    ]
    job = tmp_path / "plate.gcode"
    job.write_bytes(source.read_bytes())
    result = process(job, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.message.startswith("Stamped PLA · 3 parts · 2 layers · 3 mm")
    text = job.read_text()
    # Upper layers are byte-identical.
    assert text.split(";LAYER_CHANGE")[3:] == source.read_text().split(";LAYER_CHANGE")[3:]
