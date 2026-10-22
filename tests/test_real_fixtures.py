from pathlib import Path

import pytest

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
    after = parse("\n".join(stamped.splitlines()[1:]))
    assert sum(m.delta_e for m in original.moves) - sum(
        m.delta_e for m in after.moves
    ) == pytest.approx(result.removed_e, abs=1e-5)
    assert [m.delta_e for m in after.moves if m.delta_e < 0] == pytest.approx(
        [m.delta_e for m in original.moves if m.delta_e < 0]
    )
    assert after.moves[-1].end == pytest.approx(original.moves[-1].end)
