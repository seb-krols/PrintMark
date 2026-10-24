# Verification record

This document distinguishes software checks from tests on physical printers. It is not a
certificate of print quality or blanket firmware compatibility.

## Executed during implementation

Environment: Linux x86-64, Python 3.12.15; desktop interaction also exercised with Python
3.14.7 and Tk 8.6.16 on a virtual X display. The source checkout's managed Python uses Tk 9;
that build only exposed the fixed bitmap font on this machine, so native Tk 8.6 was used to
inspect typography and capture the actual UI screenshots. No desktop configuration was changed.

Latest automated run (Windows, 2026-10-23): **133 tests, 88% statement coverage** (one Tk
test skipped intermittently on that PC; see below). Coverage is
a description of exercised code, not a claim of complete safety or printer qualification.

- Automated tests cover relative/absolute E, relative XYZ, G92, retraction conservation,
  unchanged original upper-layer lines, CRLF preservation and malformed/unsupported commands.
- Geometry checks cover mirrored text, glyph holes, concave footprints, auto-shrink, tiny-part
  skip and a required solid roof. Removed volume is checked as filament length × filament
  cross-sectional area, rather than comparing filament length directly to cubic millimeters.
- File tests cover cancellation, disabled mode, duplicate stamping, path collisions, binary
  input, atomic-replace failure, a post-replace durability failure and audit recovery.
- Counter tests cover locking, monotonic IDs, interruption before/after replacement, missing
  pending files, exact-hash recovery from surviving final exports and idempotent CSV replay.
- Diagnostics checks cover nonmutating profile inspection, skip exit codes, last-export reports
  and protection of G-code/config/counter/log/lock paths against accidental collisions.
- Tk tests exercise drag direction in underside view, resize, rotation, invalid placement,
  Apply/Skip behavior, visible action buttons, settings persistence and part lookup.
- New v0.3 regressions cover rotation before shrinking, exact-ID lookup with Unicode/multiline
  CSV fields, JSON CLI results, missing/malformed history, lost counters, serialized ID checks,
  conflicting transaction recovery, hard-linked file collisions, UTF-8 BOM configs and escaped
  template placeholders. No malformed-log or reused-ID test changes its input G-code.
- Ruff lint/format and PyInstaller one-file build were run locally. Frozen CLI version and
  an actual stamping/audit round trip are smoke-tested by the packaging script.
- The v0.3 Linux one-file executable also passed the new JSON part-ID lookup smoke test;
  `dist/basemark-0.3.0-linux-x64.zip` was generated with documentation, licenses and checksum.
  The updated settings, diagnostics and Find part screens were inspected on a virtual Tk display.

## Real PrusaSlicer checks

PrusaSlicer `2.8.1+linux-x64-GTK3-202409181416` was downloaded from the upstream release.
Three actual generated fixtures (PLA relative E, PETG relative E, PLA absolute E) are in
`tests/fixtures/`, with provenance and a regeneration script.

The bundled `Original Prusa i3 MK3S & MK3S+` + `0.20mm QUALITY @MK3` + `Prusament PLA`
profile inheritance was resolved for a separate local integration check, with binary G-code
and arc fitting disabled. Its output successfully completed a dry run.

The actual post-processing hook was then invoked by PrusaSlicer itself:

1. `--dump-env` confirmed `SLIC3R_FILAMENT_TYPE`, quoted `SLIC3R_FILAMENT_NOTES`, layer/width
   values, `SLIC3R_PP_HOST=File`, and the final `SLIC3R_PP_OUTPUT_NAME`.
2. An auto export stamped `>PLA< T001`, consumed one ID, and wrote its final exported filename
   and object name to CSV. Both stamped G-code and underside SVG were produced.

This exercised the hook and profile syntax, not the MK3S hardware or firmware.

## Native Windows checks (2026-10-22)

Environment: Windows 11 Home 26200 x64, Windows PowerShell 5.1, uv-managed CPython 3.12.13
(Tk 8.6.12), Inno Setup 6.7.3, PrusaSlicer `2.7.4+win64-202404050928`.

- `scripts/build_windows.ps1` passed: ruff, 133 tests (one Tk test can skip intermittently
  on this PC when Tcl transiently cannot read its own script files; the reason is printed),
  one-folder PyInstaller build, frozen stamping/lookup smoke test, ZIP and installer.
- `scripts/test_windows_install.ps1` passed: silent install to a path with spaces and `é`,
  installed stamping, counter advance, settings window launch, upgrade and uninstall with
  config/counter/log preserved.
- Real PrusaSlicer 2.7.4 called the **installed** `basemark.exe` (path with spaces) as its
  post-processing script, stored in the profile as the GUI saves it. The coupon was sliced
  with the bundled `Original Prusa i3 MK3S & MK3S+` + `0.20mm QUALITY @MK3` profile
  (inheritance flattened, binary G-code and arc fitting off) with `Prusament PLA` and
  `Prusament PETG`. Both exports were stamped (`>PLA<`, `>PETG<`) with object names in
  the CSV. `--check`, `--lookup`, `--dump-env` and the minimal regression profile also
  worked from the Windows build.
- Startup: the earlier one-file executables took ~9.5 s for `--version` and ~11 s per
  export on this PC because each launch unpacked the runtime to `%TEMP%`. The one-folder
  build adds **1.6–2.5 s** per PrusaSlicer export (source run of the same check: 1.9 s).

- Prusa Buddy-firmware profiles first skipped every export on unrecognised setup commands
  (`M555` etc.). After allowing the non-motion commands `M74`, `M141`, `M142`, `M555`,
  `M569`, `M572`, `M591` and `M593`, the coupon was sliced and stamped (copies, auto mode)
  with stock profiles from **PrusaSlicer 2.9.6** (portable build): MK4S PLA and PETG,
  CORE One, MK4 Input Shaper, MK3.9S, XL Input Shaper, MINI Input Shaper and i3 MK3S.
  With PrusaSlicer 2.7.4: MK4 Input Shaper (PLA, PETG), MK4, MK3.9, XL and MINI. These
  profiles default to binary G-code and arc fitting; with either enabled, BaseMark skips
  with an explicit message (`binary/packaged G-code…`, `G2 is unsupported…`).

- Preset setup (2026-10-23): `--setup-prusaslicer` was run on a copy of a real PrusaSlicer
  2.7.4 settings folder (MK4 Input Shaper, `0.15mm STRUCTURAL @MK4IS 0.4`). PrusaSlicer
  2.9.6 then loaded the generated presets **by name** (`--datadir`, `--print-profile`,
  `--printer-profile`) and ran the installed hook (`Stamped >PLA< T001`). Its embedded
  config differed from the stock preset only in `arc_fitting`, `post_process`, the preset
  name and the inheritance chain, which named the stock preset as parent.
- With the setup applied to the real settings (copied for the test), PrusaSlicer 2.9.6
  exported the coupon in interactive mode. The placement window appeared on top, was later
  found minimized while PrusaSlicer waited (fixed in 0.4.0), and once restored and applied it
  produced `Stamped >PLA< 001` with the object name taken from `M486` labels.

This did not involve the GUI's interactive popup inside PrusaSlicer, a lab PC, or a printer.

- Pipeline check on the pilot PC (2026-10-24): a copy of the real PrusaSlicer settings
  (selected `0.15mm STRUCTURAL @MK4IS 0.4 + BaseMark` and `…MK4 Input Shaper 0.4 nozzle +
  Basemark` presets, `Generic PLA @PGIS`), the installed PrusaSlicer 2.7.4 and the installed
  BaseMark 0.4.0 exported the coupon: automatic mode stamped `>PLA< T001` with slicing
  and stamping together taking 2.4 s; interactive mode opened the export window after
  3.6 s (visible, not minimized) and stamped after the operator applied it. A reported
  “nothing happened” had no export: the part was sliced but **Export G-code** was not used.

## Performance observations

Representative single-run core timings on this development machine, using real generated
files in auto dry-run mode (includes reading, parsing, geometry and rewrite; excludes process
startup, file commit and UI):

| Input | Size | Observed core time |
| --- | ---: | ---: |
| Minimal coupon, PLA | 139,534 bytes | about 0.48 s |
| Bundled MK3S profile coupon | 188,229 bytes | about 0.50 s |
| 40 mm tall stress coupon | 717,671 bytes | about 0.79 s |
| 200 mm tall stress coupon, after parser optimization | 3,158,617 bytes | about 1.65 s |

These are observations, not cross-platform guarantees. The first version of the 3.2 MB case
took 2.6 seconds; keeping only the affected/roof move records while still interpreting the
whole file reduced it. Antivirus scanning can add time. On the Windows build PC the
one-folder build measured 1.6–2.5 s per export (see above); the **under-two-second
end-to-end target on the shop's own PCs remains to be measured**.

The locally built one-file executable completed full-process dry runs in **1.36 s** for
the minimal coupon and **1.46 s** for the MK3S-profile coupon, including extraction/startup.
The 36.8 MiB Linux archive passed a separate real write/counter/CSV smoke test. This local
development build was tested on this host; release CI builds Linux on Ubuntu 22.04 for a
more conservative runtime baseline.

## Still to be verified

- Windows and macOS CI execution and fresh-machine standalone tests. The private repository
  is now hosted at `seb-krols/PrintMark`. Initial push and manual CI/Windows runs on
  2026-10-22 ended in `startup_failure` before any job was created. No build logs or check
  annotations were exposed by the API; Actions is enabled. Local actionlint validation passed.
  See [Windows run](https://github.com/seb-krols/PrintMark/actions/runs/39834938542).
  A native Windows build has succeeded locally (above), not yet in CI. `Runner availability check` is a manual
  diagnostic with no checkout or third-party actions to isolate runner startup problems;
  [it also failed before creating a job](https://github.com/seb-krols/PrintMark/actions/runs/39835220914).
  Both PowerShell scripts pass the native PowerShell parser. Account/Actions access needs
  investigation in GitHub's signed-in UI; the API does not identify the cause.
- The owner's exact Windows/PrusaSlicer version and both MK3S and Bambu printer profiles.
  PrusaSlicer 2.7.4 with stock MK3S profiles is covered above; Bambu is not.
- Interactive export (placement popup) from the PrusaSlicer GUI on the actual Windows PCs;
  no-display fallback on their automation hosts.
- Manual inspection of the exported file in PrusaSlicer G-code Viewer on the shop PC.
- All physical tests: legibility, bead/ooze effects, bridging, adhesion, mechanical and mating
  surface effects, and failed-print material sorting.
- Network counters, proprietary Bambu commands/packaging, OrcaSlicer and arc fitting.

Use `docs/lab-validation.md` and the coupon STL for the remaining lab work.
