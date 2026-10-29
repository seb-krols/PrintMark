# BaseMark reference

Settings, command line, record files and the supported G-code. For everyday use see the
[README](../README.md).

## Settings

The BaseMark app edits these; changes apply once you click **Save changes**. They are stored
in a TOML file:

- Windows: `%APPDATA%\BaseMark\config.toml`
- Linux/macOS: `~/.config/basemark/config.toml` (respects `XDG_CONFIG_HOME`)
- Any OS: `--config /path/to/config.toml`

The file holds only values that differ from the defaults, so improved defaults reach existing
installs. An example is [examples/config.toml](../examples/config.toml). Precedence:
**built-in defaults → config file → filament notes → command-line options**.

| Setting | Default | In the app | Meaning |
| --- | --- | --- | --- |
| `enabled` | `true` | Overview | Master switch |
| `mode` | `"interactive"` | Overview | Export window (`"interactive"`) or automatic placement (`"auto"`) |
| `notify` | `true` | Overview | Corner notice after each export |
| `warn_unstamped` | `true` | Overview | Background warning for exports made without BaseMark |
| `template` | `"{material}"` | Overview, Stamp | Label text. `"{material} {id}"` adds the part number; `{date}` the export date |
| `every_part` | `true` | Stamp | A label on every part of the plate; `false` = largest part only |
| `text_height_mm` | `3.0` | Stamp | Capital-letter height, 2–12 mm |
| `min_text_height_mm` | `3.0` | Stamp | Automatic placement may shrink the text to this size |
| `layers` | `2` | Stamp | Recess depth, 1–3 layers (one more solid layer is needed above) |
| `margin_mm` | `1.5` | Stamp | Distance from first-layer edges and holes; at least 0.5 mm |
| `counter_next` | `1` | Advanced | Next part number; can only move forward |
| `counter_digits` | `3` | Advanced | Minimum digits, zero-padded; never truncates |
| `counter_prefix` | `""` | config file | Text before every number, only if several PCs stamp numbers |
| `counter_file` | `""` | Advanced | Defaults to `counter.json` next to the config |
| `log_file` | `""` | Advanced | Defaults to `log.csv` next to the config |
| `material_map` | `{}` | Advanced | Filament-name aliases, e.g. `{ PET = "PETG" }` |
| `label` | `""` | filament notes | Explicit material-name override |

### Per filament: notes in PrusaSlicer

A filament preset's **Notes** can override settings for that material, on one line:

```text
basemark: layers=2; size=4; label=PETG
```

Accepted keys: `enabled`, `mode`, `layers`, `size` (text height), `margin`, `template`,
`label`, `text_height_mm`, `min_text_height_mm`, `margin_mm`. Use `label` only when it
accurately describes the filament.

## Records

Everything lives in the BaseMark folder (`%APPDATA%\BaseMark\` on Windows):

| File | Contents |
| --- | --- |
| `config.toml` | Settings |
| `counter.json` | The next part number, plus a journal that finishes an interrupted export |
| `log.csv` | One row per numbered export: ID, UTC time, material, export name, objects, computer, layers, text height, removed filament, SHA-256 of the file |
| `last-export.json` | The latest export's result, shown on the Overview |
| `watcher.lock` | Held by the background export check while it runs |

Only exports with part numbers use the counter and the log. With several parts on a plate,
all parts carry the export's number and the row lists every object.

Before replacing G-code, BaseMark checks that the CSV is readable and the new ID is not
already recorded, so a lost counter cannot reuse an ID present in that log. It cannot detect
IDs from a deleted or different CSV: back up the folder with the shop's records. Use local
disks; a counter on a network drive is not safe. See [recovery](recovery.md) before editing
counter files by hand.

## Command line

`basemark.exe` (console) is the program PrusaSlicer runs; `basemark-desktop.exe` opens the
app without a console window. When run by PrusaSlicer, the G-code path is the **last
argument**; the file is replaced only after every check passes.

```sh
basemark job.gcode                                        # stamp (what PrusaSlicer runs)
basemark --mode auto --template "{material} {id}" job.gcode  # one-off options
basemark --off job.gcode                                  # leave this job unchanged
basemark --check job.gcode                                # test only; exit 2 if it would skip
basemark --mode auto --dry-run --preview-output p.svg job.gcode  # SVG of the labels
basemark --lookup 042 [--json]                            # find a part number
basemark --setup-prusaslicer                              # add "+ BaseMark" presets (exit 3 while PrusaSlicer is open)
basemark --check-prusaslicer                              # exit 0 ready, 2 needs fixing
basemark --watch                                          # the background export check
basemark --stop-watcher                                   # end it (the installer does this)
basemark --demo                                           # the export window with a sample plate
basemark --dump-env job.gcode                             # save the slicer's settings; no stamp
```

`--lookup` exits 0 when found, 1 when not found or the log cannot be read. `--dump-env`
writes relevant slicer variables to `environment.json` next to the config and omits unrelated
settings such as printer-host credentials; `--dump-all-env` includes everything and **may
contain secrets**. Run `basemark --help` for every option.

## The background export check

The Windows installer starts `basemark-desktop.exe --watch` at login (Startup folder entry
*BaseMark export check*). Every 2 seconds it lists new `.gcode`/`.bgcode` files in
PrusaSlicer's last export folder, its last removable-drive folder, Downloads and Desktop.
Once a file stops changing, it reads the first 4 KB and the last 512 KB. PrusaSlicer files
whose `post_process` setting doesn't mention BaseMark, and binary `.bgcode` files, produce
an *Exported without BaseMark* notice. Files BaseMark stamped or already reported are
ignored. It never changes files. `warn_unstamped = false` silences it; it then only idles.
Uploads with **Send to printer** leave no local file and cannot be checked.

## Supported G-code

- PrusaSlicer layer, feature and width comments; single material, single tool, linear planar
  extrusion; explicit `G90`/`G91`, `M82`/`M83`, and `G92 E` handling.
- Parts: objects named by PrusaSlicer's *Label objects* (`; printing object` comments or
  `M486` firmware labels). Without labels, each separate first-layer island. Each part is
  labelled on its largest island, preserving holes. Skirt, brim, purge, support and wipe
  paths are never touched.
- Requires solid deposited coverage through all stamped layers **and a solid roof layer**.
  Thin parts, sparse bottoms, narrow footprints and labels that do not fit are skipped.
- Unsupported or uncertain input leaves G-code unchanged, warns on stderr and exits 0.
  Invalid command-line syntax exits non-zero, so a broken hook is visible.
- Arcs, binary `.bgcode`, `.gcode.3mf`, sequential objects, vase mode, multiple tools or
  materials, unknown commands, firmware retraction and volumetric E are safe skips.
- After `G90`/`G91`, an explicit `M82`/`M83` is required because firmware interpretations
  differ.
- Absolute-E edits insert `G92 E…` to restore the original logical coordinate. Later
  original lines remain byte-identical. No compensating extrusion is added.

This is **toolpath subtraction**, not a reslice: no new bridges or retractions are planned.
Bead width and ooze can soften lettering. Adhesion, thin walls, sealing surfaces, strength
and bridge quality need physical testing. "Never corrupt a print" is a design goal, not a
guarantee that software testing can establish.
