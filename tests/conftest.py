from __future__ import annotations

import math
from pathlib import Path

import pytest


def coupon(*, absolute=False, relative_xyz=False, width=80, depth=35, layers=4, spacing=0.4):
    """Synthetic test program. Not a printer profile or a printer-ready file."""
    lines = [
        "; synthetic BaseMark test coupon; DO NOT PRINT",
        "G21",
        "G90",
        "M82" if absolute else "M83",
        "G92 E0",
        "G1 X0 Y0 Z0.2 F6000",
    ]
    e, x, y, z = 0.0, 0.0, 0.0, 0.2
    if relative_xyz:
        lines += ["G91", "M82" if absolute else "M83"]

    def move(nx, ny, nz, extrusion=None, comment=""):
        nonlocal x, y, z, e
        a, b, c = (nx - x, ny - y, nz - z) if relative_xyz else (nx, ny, nz)
        line = f"G1 X{a:.6f} Y{b:.6f} Z{c:.6f}"
        if extrusion is not None:
            e += extrusion
            line += f" E{e if absolute else extrusion:.9f}"
        lines.append(line + " F1800" + comment)
        x, y, z = nx, ny, nz

    move(2, 0, 0.2, 0.2, " ; purge untouched")
    for layer in range(layers):
        zval = round(0.2 * (layer + 1), 4)
        lines += [";LAYER_CHANGE", f";Z:{zval}", ";HEIGHT:0.2", ";TYPE:Skirt/Brim", ";WIDTH:0.45"]
        move(5, 5, zval)
        move(10, 5, zval, 0.2, " ; skirt untouched")
        lines += ["; printing object coupon.stl id:0 copy 0", ";TYPE:Solid infill"]
        for row in range(round(depth / spacing) + 1):
            yy = 10 + row * spacing
            start, end = (10, 10 + width) if row % 2 == 0 else (10 + width, 10)
            move(start, yy, zval)
            extrusion = width * spacing * 0.2 / (math.pi * (1.75 / 2) ** 2)
            move(end, yy, zval, extrusion)
        # Exercise retract / unretract at each boundary.
        e -= 0.8
        lines.append(f"G1 E{e if absolute else -0.8:.9f} F2400 ; retract")
        e += 0.8
        lines.append(f"G1 E{e if absolute else 0.8:.9f} F2400 ; unretract")
    lines += [
        "M104 S0",
        "M140 S0",
        "M84",
        "; filament_type = PLA",
        "; nozzle_diameter = 0.4",
        "; first_layer_extrusion_width = 0.45",
        "; filament_diameter = 1.75",
        "; gcode_flavor = marlin",
        "; complete_objects = 0",
        "; spiral_vase = 0",
    ]
    return "\n".join(lines) + "\n"


def plate(sizes=((30, 14), (30, 14), (30, 14)), *, labels="octoprint", layers=4, spacing=0.4):
    """Synthetic plate of several rectangular parts in a row. Not printer-ready.

    labels: "octoprint" comments, "firmware" M486 labels, or None (no object labels).
    """
    lines = ["; synthetic BaseMark test plate; DO NOT PRINT", "G21", "G90", "M83", "G92 E0"]
    if labels == "firmware":
        for n in range(len(sizes)):
            lines += [f"M486 S{n}", f"M486 Apart{n + 1}.stl"]
        lines.append("M486 S-1")
    lines.append("G1 X0 Y0 Z0.2 F6000")
    for layer in range(layers):
        z = round(0.2 * (layer + 1), 4)
        lines += [";LAYER_CHANGE", f";Z:{z}", ";HEIGHT:0.2", ";WIDTH:0.45"]
        left = 10
        for n, (width, depth) in enumerate(sizes):
            name = f"part{n + 1}.stl id:{n} copy 0"
            if labels == "octoprint":
                lines.append(f"; printing object {name}")
            elif labels == "firmware":
                lines.append(f"M486 S{n}")
            lines.append(";TYPE:Solid infill")
            for row in range(round(depth / spacing) + 1):
                y = 10 + row * spacing
                start, end = (left, left + width) if row % 2 == 0 else (left + width, left)
                extrusion = width * spacing * 0.2 / (math.pi * (1.75 / 2) ** 2)
                lines.append(f"G1 X{start:.4f} Y{y:.4f} Z{z} F6000")
                lines.append(f"G1 X{end:.4f} Y{y:.4f} E{extrusion:.6f} F1800")
            if labels == "octoprint":
                lines.append(f"; stop printing object {name}")
            elif labels == "firmware":
                lines.append("M486 S-1")
            left += width + 10
    lines += ["M84", "; filament_type = PLA", "; first_layer_extrusion_width = 0.45"]
    return "\n".join(lines) + "\n"


def outline_lines(text):
    """Line numbers of the letter outlines BaseMark inserts (its own block of moves)."""
    found, inside, types = set(), False, 0
    for n, line in enumerate(text.splitlines()):
        if line.startswith("; BaseMark letter outlines"):
            inside, types = True, 0
        elif inside:
            found.add(n)
            if line.startswith(";TYPE:"):
                types += 1
                inside = types < 2  # the block ends by restoring the slicer's ;TYPE
    return found


def retractions_kept(original, after, text):
    """The slicer's retractions are untouched; every one BaseMark adds is undone."""
    inserted = outline_lines(text)
    kept = [m.delta_e for m in after.moves if m.delta_e < 0 and m.index not in inserted]
    added = [m.delta_e for m in after.moves if m.length < 1e-9 and m.index in inserted]
    return kept == pytest.approx([m.delta_e for m in original.moves if m.delta_e < 0]) and (
        sum(added) == pytest.approx(0, abs=1e-6)
    )


@pytest.fixture
def gcode():
    return coupon()


@pytest.fixture
def job_file(tmp_path: Path, gcode):
    path = tmp_path / "job.gcode"
    path.write_text(gcode, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def notices(monkeypatch):
    """Record export notices instead of opening windows during tests."""
    shown = []
    monkeypatch.setattr(
        "basemark.notify.spawn", lambda config, status, message, source: shown.append(status)
    )
    return shown
