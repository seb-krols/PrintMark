from pathlib import Path

import pytest
from conftest import added_retractions, letter_crossings, outline_lines, retractions_kept
from shapely import affinity

from basemark.footprint import plate_parts
from basemark.gcode_parser import parse
from basemark.gcode_writer import rewrite
from basemark.service import process
from basemark.text_geom import text_polygons

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["pla-relative", "petg-relative", "pla-absolute"])
def test_real_prusaslicer_output(name, tmp_path):
    source = (FIXTURES / f"prusaslicer-2.8.1-{name}.gcode").read_bytes()
    target = tmp_path / "input.gcode"
    target.write_bytes(source)
    original = parse(source.decode())
    result = process(target, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.status == "stamped"
    stamped = target.read_text()
    # Original lines on the roof and every later layer are exactly preserved.
    assert stamped.split(";LAYER_CHANGE")[3:] == source.decode().split(";LAYER_CHANGE")[3:]
    body = "\n".join(stamped.splitlines()[1:])
    after = parse(body)
    assert sum(m.delta_e for m in original.moves) - sum(
        m.delta_e for m in after.moves
    ) == pytest.approx(result.removed_e, abs=1e-5)
    assert retractions_kept(original, after)
    assert outline_lines(body)  # the letters got their walls
    assert after.moves[-1].end == pytest.approx(original.moves[-1].end)


@pytest.mark.parametrize("name", ["pla-relative", "petg-relative", "pla-absolute"])
def test_real_slices_go_around_the_letters(name):
    text = (FIXTURES / f"prusaslicer-2.8.1-{name}.gcode").read_text()
    program = parse(text, retain_layers=3)
    footprint, _ = plate_parts(program, 2, 1.5, every_part=False)
    centre = footprint.representative_point()
    label = affinity.translate(text_polygons("PLA", 4.0), centre.x, centre.y)
    stamped = rewrite(program, label, 2, "PLA").text
    after = parse("\n".join(stamped.splitlines()[1:]), retain_layers=3)
    seen, primes = letter_crossings(after, label)
    assert all(retracted for _, retracted in seen)
    assert added_retractions(after) <= 30  # both layers: a handful, not one per line
    assert not primes


@pytest.mark.parametrize("name", ["pla-relative", "petg-relative", "pla-absolute"])
@pytest.mark.parametrize("retain", [None, 3])
def test_plain_move_fast_path_matches_general_parser(name, retain, monkeypatch):
    import re

    from basemark import gcode_parser

    text = (FIXTURES / f"prusaslicer-2.8.1-{name}.gcode").read_text()
    fast = parse(text, retain_layers=retain)
    monkeypatch.setattr(gcode_parser, "PLAIN_G1", re.compile(r"(?!)"))
    assert parse(text, retain_layers=retain) == fast


@pytest.mark.parametrize("move", ["G1 X1 X2 E.1", "G1 X" + "9" * 400 + " E.1"])
def test_fast_path_rejects_duplicate_and_overflowing_words(move):
    from basemark.errors import SafeSkip

    text = (FIXTURES / "prusaslicer-2.8.1-pla-relative.gcode").read_text()
    head, _, tail = text.partition(";LAYER_CHANGE")
    with pytest.raises(SafeSkip, match="malformed motion"):
        parse(head + move + "\n;LAYER_CHANGE" + tail)
