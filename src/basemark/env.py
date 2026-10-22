from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from .config import Settings
from .errors import SafeSkip

DIAGNOSTIC_KEYS = (
    "FILAMENT_TYPE",
    "FILAMENT_NOTES",
    "LAYER_HEIGHT",
    "FIRST_LAYER_HEIGHT",
    "FIRST_LAYER_EXTRUSION_WIDTH",
    "EXTRUSION_WIDTH",
    "NOZZLE_DIAMETER",
    "FILAMENT_DIAMETER",
    "GCODE_FLAVOR",
    "USE_RELATIVE_E_DISTANCES",
    "BINARY_GCODE",
    "SPIRAL_VASE",
    "COMPLETE_OBJECTS",
    "ARC_FITTING",
    "PP_HOST",
    "PP_OUTPUT_NAME",
    "BOTTOM_SOLID_LAYERS",
)


def diagnostic_env(env: dict[str, str], all_keys: bool = False) -> str:
    keys = (
        sorted(k for k in env if k.startswith("SLIC3R_"))
        if all_keys
        else ("SLIC3R_" + k for k in DIAGNOSTIC_KEYS)
    )
    return json.dumps({k: env[k] for k in keys if k in env}, indent=2, ensure_ascii=False)


def metadata(text: str) -> dict[str, str]:
    # Exported config is a fallback for standalone use. Slicer environment wins.
    return {
        m[1].upper(): m[2].strip() for m in re.finditer(r"^; ([a-z_]+) = (.*)$", text, re.MULTILINE)
    }


@dataclass(frozen=True)
class Job:
    material: str
    width: float
    nozzle: float
    filament_diameter: float
    output_name: str
    notes: str


def job_from(env: dict[str, str], text: str, settings: Settings, filename: str) -> Job:
    config = metadata(text)
    config.update({k.removeprefix("SLIC3R_"): v for k, v in env.items() if k.startswith("SLIC3R_")})
    for key in ("SPIRAL_VASE", "COMPLETE_OBJECTS", "BINARY_GCODE"):
        if config.get(key, "0").lower() not in ("0", "false", ""):
            raise SafeSkip(f"{key.lower()} is unsupported; use ordinary simultaneous ASCII slicing")
    flavor = config.get("GCODE_FLAVOR", "marlin").lower()
    if flavor not in ("marlin", "marlin2", "reprap", "prusa"):
        raise SafeSkip(f"untested G-code dialect: {flavor}")
    raw_material = config.get("FILAMENT_TYPE", "").strip().strip('"')
    if not raw_material or any(c in raw_material for c in ";,"):
        raise SafeSkip(
            "a single filament type is required; check SLIC3R_FILAMENT_TYPE with --dump-env"
        )
    material = settings.label or settings.material_map.get(raw_material, raw_material)
    if not re.fullmatch(r"[A-Za-z0-9+_.-]{1,24}", material):
        raise SafeSkip("material label must be 1–24 simple letters/numbers (+ _ . - allowed)")

    def number(key: str, fallback: float) -> float:
        raw = config.get(key, str(fallback))
        try:
            value = float(raw)
        except ValueError as exc:
            raise SafeSkip(f"unsupported {key.lower()}: {raw}") from exc
        if not math.isfinite(value) or value <= 0:
            raise SafeSkip(f"invalid {key.lower()}: {raw}")
        return value

    nozzle = number("NOZZLE_DIAMETER", 0.4)
    width_raw = config.get("FIRST_LAYER_EXTRUSION_WIDTH", "0")
    height_raw = config.get("FIRST_LAYER_HEIGHT", "0.2")
    if height_raw.endswith("%"):
        height = number("LAYER_HEIGHT", 0.2) * float(height_raw[:-1]) / 100
    else:
        height = float(height_raw)
    width = float(width_raw[:-1]) * height / 100 if width_raw.endswith("%") else float(width_raw)
    if width == 0:
        width = nozzle * 1.125  # ;WIDTH annotations, when present, override this estimate.
    if not math.isfinite(width) or not 0.1 <= width <= 2 or not 0.1 <= nozzle <= 1.2:
        raise SafeSkip("extrusion/nozzle width is outside the supported range")
    return Job(
        material,
        width,
        nozzle,
        number("FILAMENT_DIAMETER", 1.75),
        config.get("PP_OUTPUT_NAME", filename),
        config.get("FILAMENT_NOTES", ""),
    )
