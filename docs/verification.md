# Verification record

This document distinguishes software checks from tests on physical printers. It is not a
certificate of print quality or blanket firmware compatibility.

## Executed during implementation

Environment: Linux x86-64, Python 3.12.15; desktop interaction also exercised with Python
3.14.7 and Tk 8.6.16 on a virtual X display. The source checkout's managed Python uses Tk 9;
that build only exposed the fixed bitmap font on this machine, so native Tk 8.6 was used to
inspect typography and capture the actual UI screenshots. No desktop configuration was changed.

Latest automated run: **132 passing tests, 89% statement coverage**. Coverage is
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
whole file reduced it. Windows one-file extraction and antivirus scanning can add time.
The **under-two-second end-to-end target on shop PCs remains to be measured**.

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
  No native Windows build has succeeded yet. `Runner availability check` is a manual
  diagnostic with no checkout or third-party actions to isolate runner startup problems;
  [it also failed before creating a job](https://github.com/seb-krols/PrintMark/actions/runs/39835220914).
  Both PowerShell scripts pass the native PowerShell parser. Account/Actions access needs
  investigation in GitHub's signed-in UI; the API does not identify the cause.
- The owner's exact Windows/PrusaSlicer version and both MK3S and Bambu printer profiles.
- Interactive export on the actual Windows PCs; no-display fallback on their automation hosts.
- Manual inspection of the exported file in PrusaSlicer G-code Viewer on the shop PC.
- All physical tests: legibility, bead/ooze effects, bridging, adhesion, mechanical and mating
  surface effects, and failed-print material sorting.
- Network counters, proprietary Bambu commands/packaging, OrcaSlicer and arc fitting.

Use `docs/lab-validation.md` and the coupon STL for the remaining lab work.
