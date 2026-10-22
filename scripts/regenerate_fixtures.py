"""Generate real slicer output from our original coupon and minimal regression profile.

Usage: python scripts/regenerate_fixtures.py /path/to/prusa-slicer
Do not use these fixtures as machine profiles. Slice examples/basemark-coupon.stl
with the shop's configured printer instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(executable: str):
    for material, absolute in [("PLA", False), ("PETG", False), ("PLA", True)]:
        mode = "absolute" if absolute else "relative"
        destination = ROOT / "tests/fixtures" / f"prusaslicer-2.8.1-{material.lower()}-{mode}.gcode"
        args = [
            executable,
            "--load",
            str(ROOT / "tests/fixtures/coupon.ini"),
            "--filament-type",
            material,
            "--export-gcode",
            "--output",
            str(destination),
        ]
        if absolute:
            args += [
                "--no-use-relative-e-distances",
                "--start-gcode",
                "G21\nG90\nM82\nG92 E0\nG1 X0 Y0 Z0.2 F6000",
                "--layer-gcode",
                "",
            ]
        args.append(str(ROOT / "examples/basemark-coupon.stl"))
        subprocess.run(args, check=True)
    print("Fixtures generated. Record slicer version and hashes in tests/fixtures/README.md.")


if __name__ == "__main__":
    main(sys.argv[1])
