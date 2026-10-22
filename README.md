# PrintMark / BaseMark

**Material identity, printed in.** Automatic material and part-ID stamps for PrusaSlicer.

BaseMark removes small sections of extrusion from the bottom layers of a part to mark it
with its selected filament and a running identifier, such as `>PETG< A042`. Even a failed
print that retains its stamped base can carry its material identity into the recycling stream.

Built at the UBC IGEN 3D Print Shop by Sebastians Krols.

**Status: v0.2 lab pilot.** PrintMark is the repository; BaseMark is the application name.
Software verification is separate from physical qualification.
MK3S and Bambu plain-G-code workflows must be checked with the shop's actual profiles.
This is not yet a production-qualified printer accessory.

![BaseMark placement window, showing a stamp from below](docs/images/placement.png)

## Start here

1. Download the artifact from the latest successful [Windows build](https://github.com/seb-krols/PrintMark/actions/workflows/windows.yml)
   and run its `basemark-…-setup.exe`. A portable ZIP is also included; neither needs Python.
2. Open **BaseMark Settings** from Start, assign each PC a unique prefix (`A`, `B`, …), and
   copy the command from **PrusaSlicer setup** into your print preset's post-processing scripts.
3. Export a small coupon with plain G-code and arc fitting disabled. Check **Diagnostics**,
   inspect the final output in G-code Viewer, then qualify it on your printer and sheet.

**[Windows installation and troubleshooting guide →](INSTALL.md)**

Windows builds include a per-user installer, a quiet settings launcher and a console executable
for the slicer hook. They are currently unsigned. macOS/Linux portable executables can be
built by the release workflow; macOS builds are not notarized `.app` bundles.

PrusaSlicer waits for the placement window. Drag the stamp, use **+/−** to resize,
**R** to rotate 90°, or choose **Auto place**. **Enter** applies; **Esc** or **Skip label**
exports unchanged and consumes no ID. Both the footprint and text are shown **from below**.
The G-code itself contains mirrored text. A missing display falls back to auto placement.

## Develop or try it from source

```sh
uv sync --extra dev
uv run basemark --demo
uv run basemark --settings
uv run pytest
uv run ruff check .
```

Python 3.11+ and Tk are required for source installations. On Linux, install your distribution's
Python Tk package if necessary. `uv` is optional: `python -m pip install -e '.[dev]'` also works.

```sh
# SVG preview: no G-code modification and no counter increment
basemark --mode auto --dry-run --preview-output preview.svg job.gcode

# Stamp a copy for inspection
basemark --mode auto --prefix A job-copy.gcode

# Per-job opt-out (bypasses even an invalid config)
basemark --off job.gcode

# Run from PrusaSlicer once to check actual profile/environment values
basemark --dump-env job.gcode
```

Run `basemark --help` for arguments. The input path is the **last argument** when invoked
by PrusaSlicer. Its temporary file is atomically replaced only after all validation succeeds.
Standalone use reads PrusaSlicer's embedded config if environment variables are absent.

## Settings

Precedence: **built-in defaults → TOML config → filament notes → CLI arguments**.

Config locations:

- Windows: `%APPDATA%\BaseMark\config.toml`
- Linux/macOS: `~/.config/basemark/config.toml` (respects `XDG_CONFIG_HOME`)
- Any OS: `--config /path/to/config.toml`

The settings window writes the TOML file. A complete example is [examples/config.toml](examples/config.toml).
Filament notes can contain `basemark: layers=2; size=6; label=PETG`. `label` is an explicit
operator override; use it only when it accurately describes the filament. Material aliases
can also be configured with `material_map = { PET = "PETG" }`.

![BaseMark lab settings](docs/images/settings.png)

| Setting | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Master switch |
| `mode` | `"interactive"` | Placement popup or `"auto"` |
| `template` | `">{material}< {id}"` | Requires material and ID; also supports date and prefix |
| `text_height_mm` | `6.0` | Font cap height, 4–12 mm |
| `min_text_height_mm` | `4.0` | Minimum auto-shrink size |
| `layers` | `2` | Recess depth, 1–3 layers |
| `margin_mm` | `2.0` | Distance from first-layer edges/holes; at least 0.5 mm |
| `counter_prefix` | `""` | Unique computer identifier |
| `counter_digits` | `3` | Minimum zero-padding; never truncates larger IDs |
| `counter_next` | `1` | Starting value / lower bound; stored counter is authoritative |
| `counter_file` | `""` | Defaults to `counter.json` next to config |
| `log_file` | `""` | Defaults to `log.csv` next to config |
| `material_map` | `{}` | Explicit filament-name aliases |
| `label` | `""` | Optional explicit material-name override |

Relative counter/log paths resolve beside the config file. Use **local disks** for this pilot;
network shares and cross-machine coordination are outside this release. The counter cannot
be moved backwards through settings. For a new numbering series, choose a new prefix and
counter file. `{id}` includes the prefix; `{prefix}{id}` will deliberately repeat it.

The CSV records ID, UTC time, material, final export name when available, object comments,
hostname, layer count, text height, removed filament length and output SHA-256. A journal
recovers interruptions between file replacement and counter/log updates. See
[recovery procedures](docs/recovery.md) before manually altering counter files.

The **Diagnostics** tab shows the last export result, checks an original G-code file without
consuming an ID, and recovers interrupted audits from an exact matching final export.
`basemark --check job.gcode` performs the same compatibility check (exit 2 on unsupported input).

`--dump-env` writes relevant slicer variables to `environment.json` beside the config and
does not stamp. It omits unrelated slicer settings such as host credentials. `--dump-all-env`
is an explicit full SLIC3R diagnostic dump and **may contain secrets**; review before sharing.

## Supported scope and safe skips

- PrusaSlicer layer, feature and width comments; single material, single tool, linear planar
  extrusion; explicit `G90`/`G91`, `M82`/`M83`, and `G92 E` handling.
- Largest **deposited first-layer island**, preserving holes and excluding skirt, brim, purge,
  support and wipe paths. Multiple separate islands receive **one stamp total**.
- Requires solid deposited coverage through all stamped layers **and a solid roof layer**.
  Thin parts, sparse bottoms, narrow footprints and labels that do not fit are skipped.
- Unsupported or uncertain input leaves G-code unchanged, warns on stderr and exits 0.
  Invalid CLI syntax exits nonzero, so a broken hook is visible instead of silently ignored.
- Arcs, binary `.bgcode`, `.gcode.3mf`, sequential objects, vase mode, multiple tools/materials,
  unknown commands, firmware retraction and volumetric E are safe skips.
- After `G90`/`G91`, require explicit `M82`/`M83` because firmware interpretations differ.
- Absolute-E edits insert `G92 E…` to restore the original logical coordinate. Later original
  lines remain byte-identical. No actual compensating extrusion is added.

This is **toolpath subtraction**, not a reslice: no new bridge planning or retractions are
generated. Finite bead width and ooze can soften lettering. Adhesion, thin walls, sealing
surfaces, strength and bridge quality need physical testing. The claim “must never corrupt a
print” is a design goal, not a guarantee that software testing can establish.

PrusaSlicer's preview remains pre-processing; reopen the output in G-code Viewer.
The symbol style `>PLA<` / `>PETG<` is not a claim of ISO certification or material verification.
The label is only as accurate as the selected filament/profile.

## Project and release

The implementation uses Python, Shapely, fontTools, Tkinter, TOML, a local journal and CSV.
No cloud service, database server, telemetry or accounts are needed. Read the
[architecture decisions](docs/architecture.md), [lab test plan](docs/lab-validation.md),
and [verification report](docs/verification.md).

CI tests Windows, macOS and Linux. Every main-branch push builds and tests a Windows installer.
A version tag builds portable executables with PyInstaller
and stages a **draft** GitHub release for review. MIT covers project code; the bundled
unmodified Lato Bold font retains its [SIL Open Font License](src/basemark/assets/OFL.txt).

For recognition, publish reproducible test results and real underside photos, then discuss
the results with slicer maintainers. For a paid offering, installation, lab onboarding,
support, managed profiles and eventually a shared job registry are possible extensions.
Keep the tested offline stamping engine useful on its own. See [roadmap](docs/roadmap.md).
