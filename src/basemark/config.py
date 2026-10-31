from __future__ import annotations

import json
import math
import os
import re
import string
import tempfile
import time
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from .errors import SafeSkip


def config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "BaseMark"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "basemark"


MATERIAL_ONLY = "{material}"
NUMBERED = "{material} {id}"
# Saved files without config_version (up to 0.5.0) listed every value, defaults included.
# Values equal to those old defaults are dropped on load so the current defaults apply.
CONFIG_VERSION = 2
OLD_DEFAULTS = {
    "template": ">{material}< {id}",
    "text_height_mm": 6.0,
    "min_text_height_mm": 4.0,
    "margin_mm": 2.0,
}


def template_fields(template: str) -> set[str]:
    """Placeholders used by a label template; raises ValueError for unsupported ones."""
    found = set()
    for _, key, spec, conv in string.Formatter().parse(template):
        if key is not None and (key not in {"material", "id", "date", "prefix"} or spec or conv):
            raise ValueError("only {material}, {id}, {date}, {prefix} are supported")
        if key is not None:
            found.add(key)
    return found


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    mode: str = "interactive"
    template: str = MATERIAL_ONLY
    # Lato Bold strokes are ~0.18 x cap height: 3 mm gives ~0.55 mm strokes, just over
    # one 0.45 mm first-layer line, and ~1 mm counters. Smaller text starts to fill in.
    text_height_mm: float = 3.0
    min_text_height_mm: float = 3.0
    layers: int = 2
    # Keeps the label clear of the two outer perimeters (~0.9 mm).
    margin_mm: float = 1.5
    counter_prefix: str = ""
    counter_digits: int = 3
    counter_next: int = 1
    counter_file: str = ""
    log_file: str = ""
    material_map: dict[str, str] = field(default_factory=dict)
    label: str = ""
    notify: bool = True
    # Label every part on the plate (off: only the largest part, as before 0.7).
    every_part: bool = True
    # Background check: warn when an export comes from a preset that doesn't run BaseMark.
    warn_unstamped: bool = True

    def validate(self) -> Settings:
        if type(self.enabled) is not bool or self.mode not in {"auto", "interactive"}:
            raise SafeSkip("enabled must be true/false; mode must be auto or interactive")
        for name in ("notify", "every_part", "warn_unstamped"):
            if type(getattr(self, name)) is not bool:
                raise SafeSkip(f"{name} must be true/false")
        for name, low, high in [
            ("layers", 1, 3),
            ("counter_digits", 1, 12),
            ("counter_next", 1, 999_999_999_999),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise SafeSkip(f"{name} must be an integer from {low} to {high}")
        for name, low, high in [
            ("text_height_mm", 2, 12),
            ("min_text_height_mm", 2, 12),
            ("margin_mm", 0.5, 20),
        ]:
            value = getattr(self, name)
            if (
                type(value) not in (float, int)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise SafeSkip(f"{name} must be a finite number from {low} to {high}")
        if self.min_text_height_mm > self.text_height_mm:
            raise SafeSkip("minimum text height must not exceed text height")
        for name in ("template", "counter_prefix", "counter_file", "log_file", "label"):
            if not isinstance(getattr(self, name), str):
                raise SafeSkip(f"{name} must be text")
        if not re.fullmatch(r"[A-Za-z0-9_-]{0,12}", self.counter_prefix):
            raise SafeSkip(
                "prefix must contain at most 12 letters, numbers, underscores or hyphens"
            )
        if not isinstance(self.material_map, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in self.material_map.items()
        ):
            raise SafeSkip("material_map must map text keys to text values")
        try:
            placeholders = template_fields(self.template)
        except ValueError as exc:
            raise SafeSkip(f"invalid template: {exc}") from exc
        if "material" not in placeholders:
            raise SafeSkip("template must include {material}")
        return self

    @property
    def numbered(self) -> bool:
        """Whether labels carry a part number (and exports use up IDs)."""
        return "id" in template_fields(self.template)

    def paths(self, directory: Path) -> tuple[Path, Path]:
        def resolve(value: str, fallback: str) -> Path:
            p = Path(value).expanduser() if value else Path(fallback)
            return p if p.is_absolute() else directory / p

        return resolve(self.counter_file, "counter.json"), resolve(self.log_file, "log.csv")


ALIASES = {"size": "text_height_mm", "margin": "margin_mm", "prefix": "counter_prefix"}
NOTE_KEYS = {
    "enabled",
    "mode",
    "layers",
    "size",
    "margin",
    "template",
    "label",
    "text_height_mm",
    "min_text_height_mm",
    "margin_mm",
}


def notes_overrides(notes: str) -> dict:
    result = {}
    if notes.startswith('"'):
        try:
            notes = json.loads(notes)
        except ValueError as exc:
            raise SafeSkip("cannot decode serialized filament notes") from exc
        if not isinstance(notes, str):
            raise SafeSkip("filament notes must describe a single material")
    # PrusaSlicer serializes newlines as literal backslash-n in some versions.
    for line in notes.replace("\\n", "\n").splitlines():
        if not line.strip().lower().startswith("basemark:"):
            continue
        for item in line.split(":", 1)[1].split(";"):
            if not item.strip():
                continue
            key, sep, value = item.strip().partition("=")
            if not sep or key not in NOTE_KEYS:
                raise SafeSkip(f"unknown filament-note setting: {key}")
            key = ALIASES.get(key, key)
            value = value.strip()
            try:
                if key == "enabled":
                    if value.lower() not in ("true", "false"):
                        raise ValueError("use true or false")
                    result[key] = value.lower() == "true"
                elif key == "layers":
                    result[key] = int(value)
                elif key in {"text_height_mm", "min_text_height_mm", "margin_mm"}:
                    result[key] = float(value)
                else:
                    result[key] = value
            except ValueError as exc:
                raise SafeSkip(f"invalid filament-note setting {key}: {value}") from exc
    return result


def load_settings(path: Path, notes: str = "", overrides: dict | None = None) -> Settings:
    data = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise SafeSkip(f"cannot read config {path}: {exc}") from exc
    if data.pop("config_version", 1) < CONFIG_VERSION:
        data = {k: v for k, v in data.items() if OLD_DEFAULTS.get(k, object()) != v}
    unknown = data.keys() - {f.name for f in fields(Settings)}
    if unknown:
        raise SafeSkip(f"unknown config keys: {', '.join(sorted(unknown))}")
    data.update(notes_overrides(notes))
    data.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return Settings(**data).validate()


def replace_file(source: str | Path, target: Path, *, attempts: int = 40) -> None:
    """os.replace, retried for up to 2 s on Windows while another program has the target open.

    Windows refuses to replace an open file, and virus scanners or BaseMark's background
    check may read a new G-code file for a moment (uploads are stamped in %TEMP%).
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(0.05)


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(name, mode)
        replace_file(name, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_settings(path: Path, settings: Settings) -> None:
    """Store only what differs from the defaults, so improved defaults reach old installs."""
    defaults = asdict(Settings())
    changed = {k: v for k, v in asdict(settings.validate()).items() if defaults[k] != v}
    data = {"config_version": CONFIG_VERSION, **changed}
    atomic_write(path, tomli_w.dumps(data).encode("utf-8"))


def validate_paths(config: Path, settings: Settings, *extra: Path | None) -> None:
    """Locks are files too: creating one must never truncate input or another store."""
    counter, log = settings.paths(config.parent)
    paths = [
        config,
        counter,
        log,
        Path(str(counter) + ".lock"),
        Path(str(log) + ".lock"),
        config.parent / "last-export.json",
        config.parent / "last-export.json.lock",
    ]
    paths.extend(path for path in extra if path is not None)
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise SafeSkip("input, config, counter, log, locks and reports must use different paths")
    # resolve() detects symlinks, but two names can still be hard links to one file.
    identities = set()
    for path in resolved:
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        identity = (stat.st_dev, stat.st_ino)
        if identity in identities:
            raise SafeSkip(
                "input, config, counter, log, locks and reports must use different paths"
            )
        identities.add(identity)
