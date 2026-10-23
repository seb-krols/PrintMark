"""Check and configure PrusaSlicer presets for the BaseMark post-processing hook.

PrusaSlicer stores a user preset as a complete INI file whose `inherits` key names its
system parent. Keys missing from that file fall back to PrusaSlicer's built-in defaults,
not to the parent, so new presets are written with the parent's fully resolved values.
Existing presets are never modified; BaseMark writes separate "… + BaseMark" copies.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, atomic_write, config_dir

SUFFIX = " + BaseMark"
# Presets PrusaSlicer remembers in PrusaSlicer.ini [presets]; BaseMark edits print/printer.
KINDS = ("print", "printer", "filament")
SYSTEM_ONLY_KEYS = {"alias", "renamed_from"}


class SetupError(Exception):
    pass


@dataclass(frozen=True)
class Preset:
    kind: str
    name: str
    values: dict[str, str]
    user_file: Path | None  # None for a system (vendor bundle) preset

    @property
    def parent(self) -> str:
        return self.name if self.user_file is None else self.values.get("inherits", "")


@dataclass(frozen=True)
class Finding:
    ok: bool | None  # True = good, False = must fix, None = note
    text: str


def hook_command(config: Path | None = None) -> str:
    """The post-processing line for this installation (console exe when frozen)."""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        if executable.name.lower() == "basemark-desktop.exe":
            executable = executable.with_name("basemark.exe")
        command = f'"{executable}"'
    else:
        command = f'"{executable}" -m basemark'
    if config is not None and config != config_dir() / "config.toml":
        command += f' --config "{config}"'
    return command


def data_dir() -> Path | None:
    home = Path.home()
    if os.name == "nt":
        candidates = [Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "PrusaSlicer"]
    elif sys.platform == "darwin":
        candidates = [home / "Library/Application Support/PrusaSlicer"]
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        candidates = [xdg / "PrusaSlicer", home / ".PrusaSlicer"]
    return next((path for path in candidates if (path / "PrusaSlicer.ini").is_file()), None)


def read_ini(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {"": {}}
    current = sections[""]
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return sections


def selected(data: Path) -> dict[str, str]:
    presets = read_ini(data / "PrusaSlicer.ini").get("presets", {})
    return {kind: presets.get(kind, "") for kind in KINDS}


def bundle_files(data: Path) -> list[Path]:
    files = sorted((data / "vendor").glob("*.ini"))
    roots = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
            if base:
                roots.append(Path(base) / "Prusa3D/PrusaSlicer/resources/profiles")
    elif sys.platform == "darwin":
        roots.append(Path("/Applications/PrusaSlicer.app/Contents/Resources/profiles"))
    for root in roots:
        files += sorted(root.glob("*.ini"))
    return files


def resolve(sections: dict, kind: str, name: str, seen: frozenset = frozenset()) -> dict:
    if name in seen:
        raise SetupError(f"Circular inheritance in {kind} preset “{name}”")
    own = dict(sections[f"{kind}:{name}"])
    merged: dict[str, str] = {}
    for parent in filter(None, (p.strip() for p in own.pop("inherits", "").split(";"))):
        if f"{kind}:{parent}" not in sections:
            raise SetupError(f"{kind} preset “{name}” inherits missing “{parent}”")
        merged.update(resolve(sections, kind, parent, seen | {name}))
    merged.update(own)
    return merged


def load_preset(data: Path, kind: str, name: str) -> Preset:
    if not name:
        raise SetupError(f"PrusaSlicer has no {kind} preset selected yet.")
    user = data / kind / f"{name}.ini"
    if user.is_file():
        return Preset(kind, name, read_ini(user)[""], user)
    for bundle in bundle_files(data):
        sections = read_ini(bundle)
        if f"{kind}:{name}" in sections:
            values = resolve(sections, kind, name)
            return Preset(kind, name, {k: v for k, v in values.items() if k != "inherits"}, None)
    raise SetupError(f"Cannot find the PrusaSlicer {kind} preset “{name}”.")


def split_strings(value: str) -> list[str]:
    """Decode PrusaSlicer's C-style string list, e.g. `"a b";c`."""
    items, i, value = [], 0, value.strip()
    while i < len(value):
        if value[i] == '"':
            i, chars = i + 1, []
            while i < len(value) and value[i] != '"':
                if value[i] == "\\" and i + 1 < len(value):
                    i += 1
                    chars.append({"n": "\n", "r": "\r", "t": "\t"}.get(value[i], value[i]))
                else:
                    chars.append(value[i])
                i += 1
            items.append("".join(chars))
            end = value.find(";", i)
        else:
            end = value.find(";", i)
            items.append(value[i : end if end >= 0 else len(value)].strip())
        if end < 0:
            break
        i = end + 1
    return items


def join_strings(items: list[str]) -> str:
    escaped = (
        s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
        for s in items
    )
    return ";".join(f'"{s}"' for s in escaped)


def script_lines(value: str) -> list[str]:
    # PrusaSlicer runs each non-empty line of every post_process entry as one script.
    return [line.strip() for item in split_strings(value) for line in item.splitlines()]


def is_basemark(line: str) -> bool:
    return "basemark" in line.lower()


def executable_of(line: str) -> Path:
    if line.startswith('"'):
        return Path(line[1:].partition('"')[0])
    return Path(line.split(" ", 1)[0])


def with_hook(value: str, command: str) -> str:
    lines = [line for line in script_lines(value) if line and not is_basemark(line)]
    return join_strings(["\n".join([*lines, command])])


def prusaslicer_running() -> bool | None:
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.lower()
            return "prusa-slicer" in output or "prusaslicer" in output
        result = subprocess.run(["pgrep", "-if", "prusa-?slicer"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def check(settings: Settings, command: str, data: Path | None = None) -> list[Finding]:
    data = data or data_dir()
    if data is None:
        return [Finding(False, "PrusaSlicer settings were not found. Open PrusaSlicer once first.")]
    findings = [Finding(True, f"PrusaSlicer settings: {data}")]
    if prusaslicer_running():
        findings.append(
            Finding(
                None,
                "PrusaSlicer is open. Only saved presets can be checked: save your changes "
                "(or close PrusaSlicer) and check again.",
            )
        )
    chosen = selected(data)
    try:
        print_preset = load_preset(data, "print", chosen["print"])
        printer = load_preset(data, "printer", chosen["printer"])
    except SetupError as exc:
        return [*findings, Finding(False, str(exc))]
    p, q = print_preset.values, printer.values
    hooks = [line for line in script_lines(p.get("post_process", "")) if is_basemark(line)]
    where = f"Print preset “{print_preset.name}”"
    if not hooks:
        findings.append(
            Finding(
                False,
                f"{where} has no BaseMark post-processing script, so BaseMark never runs. "
                "Use “Set up PrusaSlicer for me”, or paste the command into Print Settings → "
                "Output options → Post-processing scripts and save the preset.",
            )
        )
    else:
        exe = executable_of(hooks[0])
        if not exe.is_file():
            findings.append(Finding(False, f"{where} runs a missing program: {exe}"))
        elif hooks[0] != command:
            findings.append(
                Finding(None, f"{where} runs BaseMark with: {hooks[0]}\nThis install: {command}")
            )
        else:
            findings.append(Finding(True, f"{where} runs BaseMark after export."))
    if p.get("arc_fitting", "disabled") != "disabled":
        findings.append(
            Finding(False, f"{where}: arc fitting is on (Print Settings → Advanced → Arc fitting).")
        )
    else:
        findings.append(Finding(True, f"{where}: arc fitting is off."))
    for key, label in [("spiral_vase", "spiral vase"), ("complete_objects", "sequential printing")]:
        if p.get(key) == "1":
            findings.append(Finding(False, f"{where}: {label} is on; BaseMark will skip."))
    bottom = p.get("bottom_solid_layers", "")
    if bottom.isdigit() and int(bottom) < settings.layers + 1:
        findings.append(
            Finding(
                None,
                f"{where}: {bottom} solid bottom layers; a {settings.layers}-layer stamp "
                f"needs at least {settings.layers + 1}, so most parts will skip.",
            )
        )
    where = f"Printer preset “{printer.name}”"
    if q.get("binary_gcode", "0") != "0":
        findings.append(
            Finding(
                False,
                f"{where} exports binary G-code (Printer Settings → General → Firmware → "
                "Supports binary G-code).",
            )
        )
    else:
        findings.append(Finding(True, f"{where} exports plain G-code."))
    if len(q.get("nozzle_diameter", "0.4").split(",")) > 1:
        findings.append(
            Finding(None, f"{where} has several tools; BaseMark skips multi-tool jobs.")
        )
    if not settings.enabled:
        findings.append(Finding(False, "BaseMark stamping is switched off (Stamp tab)."))
    if not settings.counter_prefix:
        findings.append(
            Finding(None, "No computer prefix is set (Identity & records): IDs look like 001.")
        )
    return findings


def format_findings(findings: list[Finding]) -> str:
    marks = {True: "[ok]  ", False: "[fix] ", None: "[note]"}
    lines = [f"{marks[f.ok]} {f.text}" for f in findings]
    verdict = (
        "Ready: slice and use Export G-code."
        if all(f.ok is not False for f in findings)
        else "Not ready yet: fix the items marked [fix]."
    )
    return "\n".join([verdict, *lines])


def write_preset(path: Path, values: dict[str, str]) -> None:
    from . import __version__

    lines = [f"# generated by BaseMark {__version__} for PrusaSlicer"]
    lines += [f"{key} = {values[key]}" for key in sorted(values)]
    atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def derived(preset: Preset, changes: dict[str, str], id_key: str) -> tuple[str, dict[str, str]]:
    name = preset.name
    if not (preset.user_file and name.lower().endswith(SUFFIX.lower())):
        name += SUFFIX
    values = {k: v for k, v in preset.values.items() if k not in SYSTEM_ONLY_KEYS}
    values.update(changes, inherits=preset.parent, **{id_key: ""})
    return name, values


def select(data: Path, choices: dict[str, str]) -> None:
    path = data / "PrusaSlicer.ini"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    section, done = "", set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif section == "presets" and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in choices:
                ending = "\r\n" if line.endswith("\r\n") else "\n"
                lines[i] = f"{key} = {choices[key]}{ending}"
                done.add(key)
    if done != choices.keys():
        raise SetupError("PrusaSlicer.ini has no [presets] section to update.")
    backup = path.with_name("PrusaSlicer.ini.basemark-backup")
    atomic_write(backup, path.read_bytes())
    atomic_write(path, "".join(lines).encode("utf-8"))


def setup(command: str, data: Path | None = None) -> list[str]:
    """Create BaseMark copies of the selected print/printer presets and select them."""
    data = data or data_dir()
    if data is None:
        raise SetupError("PrusaSlicer settings were not found. Open PrusaSlicer once first.")
    if prusaslicer_running():
        raise SetupError(
            "Close PrusaSlicer first. It keeps presets in memory and would not see the change."
        )
    chosen = selected(data)
    print_preset = load_preset(data, "print", chosen["print"])
    printer = load_preset(data, "printer", chosen["printer"])
    done, choices = [], {}
    name, values = derived(
        print_preset,
        {
            "post_process": with_hook(print_preset.values.get("post_process", ""), command),
            "arc_fitting": "disabled",
        },
        "print_settings_id",
    )
    write_preset(data / "print" / f"{name}.ini", values)
    choices["print"] = name
    done.append(f"Print preset “{name}”: BaseMark hook added, arc fitting off.")
    if printer.values.get("binary_gcode", "0") != "0":
        name, values = derived(printer, {"binary_gcode": "0"}, "printer_settings_id")
        write_preset(data / "printer" / f"{name}.ini", values)
        choices["printer"] = name
        done.append(f"Printer preset “{name}”: plain G-code.")
    else:
        done.append(f"Printer preset “{printer.name}” already exports plain G-code.")
    select(data, choices)
    done.append("Selected in PrusaSlicer. Open PrusaSlicer, slice and use Export G-code.")
    return done
