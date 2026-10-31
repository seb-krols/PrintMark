from pathlib import Path

import pytest
from conftest import outline_lines, retractions_kept

from basemark.gcode_parser import parse
from basemark.service import process

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
    assert retractions_kept(original, after, body)
    assert outline_lines(body)  # the letters got their walls
    assert after.moves[-1].end == pytest.approx(original.moves[-1].end)


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
