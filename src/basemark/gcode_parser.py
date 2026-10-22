"""Conservative interpreter for the linear PrusaSlicer dialect.

Never infer E mode. G90/G91 invalidate E mode until M82/M83 makes firmware
semantics unambiguous. Nonlinear motion is a safe skip, not an approximation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .errors import SafeSkip

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
WORD = re.compile(rf"([A-Z])\s*({NUMBER})", re.I)
COMMAND = re.compile(r"^([GMT])(\d+(?:\.\d+)?)(?:\s|(?=[A-Z])|$)", re.I)
PART_TYPES = {
    "External perimeter",
    "Perimeter",
    "Overhang perimeter",
    "Solid infill",
    "Top solid infill",
    "Bridge infill",
    "Internal infill",
    "Gap fill",
}
SOLID_TYPES = PART_TYPES - {"Internal infill"}
# Only commands with known non-positional semantics are allowed after slicing starts.
PASSIVE = {
    "G4",
    "G21",
    "M73",
    "M104",
    "M109",
    "M140",
    "M190",
    "M106",
    "M107",
    "M201",
    "M203",
    "M204",
    "M205",
    "M220",
    "M221",
    "M900",
    "M400",
    "M117",
    "M118",
    "M486",
    "M862",
    "M84",
    "M300",
}
SETUP_ONLY = {
    "M115",
    "M92",
    "M301",
    "M304",
    "M302",
    "M17",
    "M862.1",
    "M862.2",
    "M862.3",
    "M862.4",
    "M862.5",
    "M862.6",
}


@dataclass(frozen=True, slots=True)
class Move:
    index: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    e_start: float
    e_end: float
    delta_e: float
    e_relative: bool
    xyz_relative: bool
    layer: int
    feature: str
    width: float
    params: dict[str, float]
    comment: str
    command: str
    wipe: bool = False

    @property
    def length(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def deposits(self) -> bool:
        return self.delta_e > 1e-9 and self.length > 1e-9 and not self.wipe

    @property
    def part(self) -> bool:
        return self.deposits and self.layer >= 0 and self.feature in PART_TYPES


@dataclass
class Program:
    lines: list[str]
    moves: list[Move]
    layers: int
    objects: list[str]
    newline: str


def parse(text: str, default_width: float = 0.45, *, retain_layers: int | None = None) -> Program:
    if "; BASEMARK stamp " in text:
        raise SafeSkip("this file already carries a BaseMark stamp")
    lines = text.splitlines(keepends=True)
    xyz: list[float | None] = [None, None, None]
    e: float | None = None
    e_relative: bool | None = None
    xyz_relative: bool | None = None
    layer, feature, width, wipe = -1, "", default_width, False
    z_hint, last_z_hint = None, -math.inf
    moves, objects = [], []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == ";LAYER_CHANGE":
            layer += 1
            feature, wipe, z_hint = "", False, None
        elif stripped.startswith(";Z:"):
            try:
                z_hint = float(stripped[3:])
            except ValueError as exc:
                raise SafeSkip("invalid layer Z annotation") from exc
            if not math.isfinite(z_hint) or z_hint <= last_z_hint:
                raise SafeSkip("non-increasing layers (sequential objects are unsupported)")
            last_z_hint = z_hint
        elif stripped.startswith(";TYPE:"):
            feature = stripped[6:].strip()
        elif stripped.startswith(";WIDTH:"):
            try:
                width = float(stripped[7:])
            except ValueError as exc:
                raise SafeSkip("invalid extrusion width") from exc
            if not math.isfinite(width) or not 0.1 <= width <= 2:
                raise SafeSkip("unsupported extrusion width")
        elif stripped == ";WIPE_START":
            wipe = True
        elif stripped == ";WIPE_END":
            wipe = False
        elif stripped.startswith("; printing object "):
            name = stripped.removeprefix("; printing object ")
            if name not in objects:
                objects.append(name)
        code, sep, comment = line.partition(";")
        code = code.strip()
        if not code:
            continue
        match = COMMAND.match(code)
        if not match or "*" in code:
            raise SafeSkip(f"unrecognized/numbered G-code at line {index + 1}")
        major, dot, minor = match[2].partition(".")
        command = f"{match[1].upper()}{int(major)}" + (dot + minor if dot else "")
        if command in {"M117", "M118"}:
            continue
        rest = code[match.end() :]
        words = WORD.findall(rest)
        residue = WORD.sub("", rest).strip()
        params = {key.upper(): float(value) for key, value in words}
        if command in {"G0", "G1", "G92", "G90", "G91", "M82", "M83"}:
            if (
                residue
                or len(params) != len(words)
                or any(not math.isfinite(v) for v in params.values())
            ):
                raise SafeSkip(f"malformed motion at line {index + 1}")
        if command in {"G2", "G3", "G5", "G20", "G10", "G11", "M200", "M206", "M428"}:
            raise SafeSkip(
                f"{command} is unsupported; disable arcs/volumetric E/firmware retraction"
            )
        if command in {"G90", "G91"}:
            xyz_relative = command == "G91"
            e_relative = None
        elif command in {"M82", "M83"}:
            e_relative = command == "M83"
        elif command == "G92":
            if not params or params.keys() - set("XYZE"):
                raise SafeSkip("unsupported G92 coordinate reset")
            for i, key in enumerate("XYZ"):
                if key in params:
                    if layer >= 0:
                        raise SafeSkip("XYZ coordinate resets inside a print are unsupported")
                    xyz[i] = params[key]
            if "E" in params:
                e = params["E"]
        elif command in {"G0", "G1"}:
            if params.keys() - set("XYZEF"):
                raise SafeSkip(f"unsupported motion parameters at line {index + 1}")
            if any(k in params for k in "XYZ") and xyz_relative is None:
                raise SafeSkip("XYZ positioning mode must be explicit (G90/G91)")
            start = tuple(xyz)
            for i, key in enumerate("XYZ"):
                if key in params:
                    if xyz_relative and xyz[i] is None:
                        raise SafeSkip("relative move starts at an unknown position")
                    xyz[i] = (xyz[i] + params[key]) if xyz_relative else params[key]
            e_start = e
            delta_e = 0.0
            if "E" in params:
                if e_relative is None:
                    raise SafeSkip("E mode is unknown; set M82/M83 after G90/G91")
                if not e_relative and e is None:
                    raise SafeSkip("absolute E requires an initial G92 E reset")
                e_start = e or 0.0
                delta_e = params["E"] if e_relative else params["E"] - e_start
                e = e_start + delta_e
            if layer >= 0 and delta_e > 0 and any(k in params for k in "XY"):
                if None in start or None in xyz:
                    raise SafeSkip("extrusion starts at an unknown XYZ position")
                if abs(xyz[2] - start[2]) > 1e-6:
                    raise SafeSkip("non-planar extrusion is unsupported")
                if z_hint is None or abs(xyz[2] - z_hint) > 0.001:
                    raise SafeSkip("extrusion Z disagrees with the layer annotation")
                if not feature:
                    raise SafeSkip("missing ;TYPE annotation on a print extrusion")
            # Unknown positions on initial homing/travel are never eligible for clipping.
            if retain_layers is not None and layer >= retain_layers:
                continue
            moves.append(
                Move(
                    index,
                    tuple(v or 0.0 for v in start),
                    tuple(v or 0.0 for v in xyz),
                    e_start or 0.0,
                    e or 0.0,
                    delta_e,
                    bool(e_relative),
                    bool(xyz_relative),
                    layer,
                    feature,
                    width,
                    params,
                    comment.rstrip("\r\n") if sep else "",
                    command,
                    wipe,
                )
            )
        elif command in {"G28", "G29", "G80"}:
            if layer >= 0:
                # End G-code homing is harmless once there are no further extrusions.
                feature = ""
            xyz = [None, None, None]
        elif command.startswith("T"):
            if command != "T0":
                raise SafeSkip("multiple tools are unsupported")
            if layer >= 0:
                raise SafeSkip("tool selection inside a print is unsupported")
        elif layer >= 0 and command not in PASSIVE:
            raise SafeSkip(f"unsupported in-print command {command} at line {index + 1}")
        elif command not in PASSIVE and command not in SETUP_ONLY:
            raise SafeSkip(f"unsupported setup command {command}")
    if layer < 0 or not any(m.part and m.layer == 0 for m in moves):
        raise SafeSkip("no PrusaSlicer first-layer part extrusion found")
    return Program(lines, moves, layer + 1, objects, "\r\n" if "\r\n" in text else "\n")
