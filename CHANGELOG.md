# Changes

## 0.8.0 — license: free for noncommercial use

- **License: PolyForm Noncommercial 1.0.0.** Free for hobbyists, student groups, schools,
  universities, charities and public bodies; commercial use needs a paid license.
  [LICENSING.md](LICENSING.md) explains it in plain language.
- **Free monthly allowance: 100 stamped exports per calendar month.** From 20 left, the
  *Stamped* notice counts down. Over the limit, exports are left unchanged and the notice
  *Free monthly limit reached* says whom to contact. Previews, checks and skipped exports
  don't count; a plate counts once.
- **License keys** remove the limit: free for noncommercial groups that need more, paid for
  businesses. Enter one under **Advanced → License** or with `--license-key`; `--license`
  prints the status. Keys are signed and checked offline; nothing is sent anywhere.
- The Overview shows this month's count or the license holder.
- Release archives now include LICENSING.md and Pillow's license text.

## 0.7.0 — every part on the plate, export warning

- **Every part on the plate gets a label.** Parts are told apart by PrusaSlicer's
  *Label objects* (on in Prusa's printer profiles; `; printing object` comments or `M486`
  firmware labels), otherwise by separate first-layer islands. Parts without room are left
  unstamped and the notice says *Stamped PLA on 2 of 3 parts*. With part numbers on, all
  parts of one export carry the same number and the log lists every object. **Every part on
  the plate** (Stamp page, `every_part = false`) goes back to the largest part only.
- **The export window shows the whole plate**: click a part or press Tab to select it,
  switch off **Stamp this part** to leave one out, **Zoom to this part** (Z or
  double-click) for small parts. The green button says how many parts get a label.
- **Warning for exports without BaseMark.** A small background check, started at login by
  the installer, looks at new G-code files in PrusaSlicer's export folders, Downloads and
  Desktop. A notice, *Exported without BaseMark*, names the print preset that doesn't run
  BaseMark, or flags binary G-code. Turn it off on the Overview (*Warn about exports without
  BaseMark*, `warn_unstamped = false`). The installer stops it before upgrades and on
  uninstall. New `--watch` and `--stop-watcher`.
- README rewritten for shop staff, with current screenshots; settings, command line and
  supported G-code moved to [docs/reference.md](docs/reference.md).
- Fixed: the export window's side panel no longer cuts off its last line on a plate.

## 0.6.0 — material-only labels, small text, Save button

- **Labels show just the material** (`PLA`) by default. **Add a part number** (Overview or
  Stamp) switches to `PLA 001`, `PLA 002`, …; numbers are only used, counted and logged
  when it is on. Existing installs that kept the old `>{material}< {id}` default get
  the new one; a template you chose yourself is kept.
- **Smaller default text: 3 mm** (was 6 mm, minimum 4 mm), the smallest that keeps Lato
  Bold strokes (~0.55 mm) wider than one first-layer line. Text may be set to 2–12 mm;
  the placement window's **−** goes to 2 mm by hand. Edge margin 1.5 mm (was 2 mm).
  Smallest part for `PLA`: about 10 × 6 mm (`>PLA< A001` needed about 34 × 8 mm).
- **Save button:** settings are no longer saved when a field loses focus (which missed
  edits when the window was closed, and silently rejected invalid values). Changes show
  *Unsaved changes*; **Save changes** (Ctrl+S or Enter) saves, **Discard** reverts, and
  closing with unsaved changes asks to save. Invalid values keep the window open.
- **No computer prefix:** removed from the installer, the Overview and the setup check
  (the shop has one PC). `counter_prefix` still works in `config.toml`. Removed
  `--set-prefix` and the installer's `/PREFIX`.
- The config file now stores only values that differ from the defaults
  (`config_version = 2`).
- Notices and *Recent exports* show the exported file name instead of PrusaSlicer's
  temporary `.gcode.pp` name.

## 0.5.0 — export notices and faster large files

- After each export a small notice in the screen corner says **Stamped >PLA< A001** or
  **Export not stamped** with the reason (arc moves, binary G-code, part too small, …).
  PrusaSlicer only shows a script's output when it fails, so safe skips used to be
  silent. It runs detached, so the export never waits for it. Turn it off on the
  Overview (*Show a notice after each export*) or with `notify = false`.
- Large files are about twice as fast: the parser has a fast path for plain moves and
  no longer builds temporary sets per line (6 MB job: 1.95 s → 0.86 s parsing; same
  checks, identical results on all fixtures). Slicer metadata is no longer re-scanned
  when PrusaSlicer already provides it.
- An open BaseMark window follows exports: Recent exports and the next ID update by
  themselves. Before, changing a setting after an export failed with *Next ID must be
  at least …* until the window was reopened.
- The Overview highlights a missing computer prefix.
- **One-page installer:** type this PC's prefix, keep *Connect PrusaSlicer now*
  ticked, click Install. It asks you to close PrusaSlicer if needed and leaves an
  already-working setup alone. Silent deployment for shop PCs:
  `setup.exe /VERYSILENT /PREFIX=B` (`/CONNECT=no` to skip PrusaSlicer). New CLI
  `--set-prefix`; `--setup-prusaslicer` exits 3 while PrusaSlicer is open.
- **Smooth placement preview:** the label and part outline are anti-aliased (Pillow)
  instead of jagged canvas shapes, and dragging only redraws the label, not ~5,000
  grid dots and the part outline on every mouse move. Toggles are smooth too.

## 0.4.1 — clearer export step

- The Overview says that BaseMark runs on **Export G-code** (Ctrl+G) or **Send to
  printer**, not when slicing; slicing without exporting looked like a broken setup.
- The export window takes keyboard focus when Windows would otherwise keep it behind
  another app, and flashes its taskbar button if it still cannot.

## 0.4.0 — redesigned app

- New BaseMark app layout with a sidebar: **Overview** (PrusaSlicer status with one-click
  setup and the result of every check, this PC's prefix and next ID, stamping on/off, ask vs.
  automatic placement, label preview, recent exports), **Stamp**, **Find part** (result as a
  card) and **Advanced** (numbering, record files, manual hook, check/recover tools).
- Settings save automatically when a field is left or a toggle changes; there is no Save
  button to forget. Invalid values are reported in the status bar and not saved.
- The export window (*Stamp this export*) names the G-code file, material and ID, shows a
  clear fit badge and keyboard hints, and keeps controls visible on small screens.
- Crisp text at 150–200% Windows display scaling (DPI aware, layout scaled to match).
- The export window restores itself if Windows leaves it minimized; it was seen minimized
  while PrusaSlicer waited, which looks like a hung export.
- The Start menu entry is now **BaseMark**.

## 0.3.1 — easier PrusaSlicer setup

- **Set up PrusaSlicer for me** and **Check my setup** in settings (and
  `--setup-prusaslicer` / `--check-prusaslicer`): BaseMark writes complete
  `… + BaseMark` copies of the selected print/printer presets (hook on, arc fitting and
  binary G-code off) and selects them, then lists anything the saved presets still lack.
- Firmware object labels (`M486 A…`, used by Prusa MK4/XL/MINI profiles) fill the CSV's
  object names.
- Settings and placement windows fit the usable screen area (taskbar excluded) and use a
  compact header on short screens, so Save/Apply stay visible at 150–200% scaling.
- Release checksum files use LF line endings, so `sha256sum -c` works.

## 0.3.0 — lab workflow improvements

- Added **Find part** to settings and `--lookup ID [--json]` to the CLI. Searches local or
  explicitly selected CSV history without changing G-code or consuming an ID.
- Automatic placement tries a 90° rotation before shrinking the text.
- Existing IDs, incompatible CSV headers and incomplete rows stop stamping before file
  replacement. The log lock covers the ID check through the commit; recovery detects
  conflicting transactions instead of silently accepting them.
- Config validation now detects hard-linked file collisions, accepts UTF-8 BOMs commonly
  written by Windows tools, and requires real material/ID template placeholders.
- CLI actions are mutually exclusive to prevent lookup/recovery from being mistaken for
  post-processing. Frozen package smoke tests now verify ID lookup as well as stamping.
- Windows now ships as a one-folder install (`basemark.exe` and `basemark-desktop.exe` share
  one runtime) instead of one-file executables. One-file builds unpacked ~70 MB to `%TEMP%`
  on every export: about 11 s per PrusaSlicer export on the build PC versus 1.6–2.5 s now.
  The installer drops from 59 MB to 23 MB and replaces the runtime folder on upgrade.
- Prusa Buddy-firmware printers (MK4/MK4S, MK3.9, CORE One, XL, MINI) no longer skip every
  export: their non-motion start/end commands `M74`, `M141`, `M142`, `M555`, `M569`, `M572`,
  `M591` and `M593` are now recognised. Stock PrusaSlicer 2.7.4 and 2.9.6 profiles stamp.
- On Windows, messages written to PrusaSlicer or other pipes are UTF-8 (no garbled `·`/`—`).
- Windows build scripts work in Windows PowerShell 5.1 and with per-user Inno Setup installs;
  the install test also runs outside GitHub Actions.
- 133 local tests pass. A native Windows build, install/upgrade/uninstall test and real
  PrusaSlicer 2.7.4 exports with the stock MK3S profiles passed on 2026-10-22. Physical
  printer qualification remains pending.

## 0.2.0 — initial repository pilot

- Conservative PrusaSlicer G-code parsing, mirrored text subtraction, placement UI, settings,
  local counters, CSV records and interrupted-export recovery.
- Windows installer/portable build scripts, cross-platform CI, installation guide and coupon.
- Export diagnostics and a compatibility check that does not consume an ID.
