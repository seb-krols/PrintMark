"""Smoke-test the frozen binary, then package it with licenses and lab instructions."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from basemark import __version__

ROOT = Path(__file__).resolve().parents[1]


def main(platform: str):
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        if os.environ.get("GITHUB_REF_NAME") != f"v{__version__}":
            raise RuntimeError("Release tag must match the package version in pyproject.toml")
    # Windows ships a one-folder build (dist/basemark/); other platforms a one-file binary.
    app_dir = ROOT / "dist" / "basemark"
    if not app_dir.is_dir():
        app_dir = ROOT / "dist"
    binary = app_dir / ("basemark.exe" if os.name == "nt" else "basemark")
    subprocess.run([str(binary), "--version"], check=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="basemark-smoke-") as folder:
        temp = Path(folder) / "Lab files – test"
        temp.mkdir()
        source = ROOT / "tests/fixtures/prusaslicer-2.8.1-petg-relative.gcode"
        target = temp / "coupon.gcode"
        shutil.copyfile(source, target)
        result = subprocess.run(
            [str(binary), "--config", str(temp / "config.toml"), "--mode", "auto", str(target)],
            check=True,
            timeout=30,
            capture_output=True,
            text=True,
        )
        if (
            not target.read_text(encoding="utf-8").startswith("; BASEMARK stamp")
            or "Stamped" not in result.stdout
        ):
            raise RuntimeError(
                f"Frozen stamping smoke test failed: {result.stdout} {result.stderr}"
            )
        if not (temp / "log.csv").exists():
            raise RuntimeError("Frozen binary did not produce the audit log")
        lookup = subprocess.run(
            [str(binary), "--config", str(temp / "config.toml"), "--lookup", "001", "--json"],
            check=True,
            timeout=30,
            capture_output=True,
            text=True,
        )
        records = json.loads(lookup.stdout)
        if len(records) != 1 or records[0]["material"] != "PETG":
            raise RuntimeError("Frozen part-ID lookup did not find the stamped export")
    archive = ROOT / "dist" / f"basemark-{__version__}-{platform}.zip"
    app_files = [binary]
    if app_dir != ROOT / "dist":
        app_files = sorted(p for p in app_dir.rglob("*") if p.is_file())
    files = [
        ROOT / "README.md",
        ROOT / "INSTALL.md",
        ROOT / "CHANGELOG.md",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "src/basemark/assets/OFL.txt",
        ROOT / "examples/config.toml",
        ROOT / "examples/basemark-coupon.stl",
        ROOT / "examples/lab-results.csv",
    ]
    desktop = app_dir / "basemark-desktop.exe"
    if os.name == "nt":
        if not desktop.is_file():
            raise RuntimeError("Windows package requires the desktop settings launcher")
        if desktop not in app_files:
            app_files.append(desktop)
    files += sorted(p for p in (ROOT / "docs").rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in app_files:
            bundle.write(path, path.relative_to(app_dir).as_posix())
        for path in files:
            bundle.write(path, path.relative_to(ROOT).as_posix())
        for package in ("shapely", "numpy", "fonttools", "tomli-w", "filelock", "pyinstaller"):
            dist = importlib.metadata.distribution(package)
            for entry in dist.files or []:
                if any(word in entry.name.lower() for word in ("license", "copying", "notice")):
                    bundle.write(dist.locate_file(entry), f"licenses/{package}/{entry}")
        for path in sorted((ROOT / "licenses").glob("*")):
            bundle.write(path, f"licenses/{path.name}")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    # LF endings so `sha256sum -c` also works on macOS/Linux.
    archive.with_suffix(".sha256").write_bytes(f"{sha}  {archive.name}\n".encode("ascii"))
    print(f"Verified and packaged {archive.name}")


if __name__ == "__main__":
    main(sys.argv[1])
