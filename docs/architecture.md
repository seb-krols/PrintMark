# Architecture decisions

## A local desktop post-processor

BaseMark should be a small native utility launched by the slicer. The workflow does not need
a browser, an application server, authentication or a hosted database. Keeping material
selection inside PrusaSlicer avoids another source of truth about what filament will print.

| Choice | Decision and trade-off |
| --- | --- |
| Python 3.11+ | Readable interpreter and geometry code; distributable as native executables. Native bindings do the expensive polygon work. |
| Shapely 2.x / GEOS | Buffer actual deposited paths, retain holes, intersect layers, and split line segments. No convex-hull approximation. |
| fontTools + bundled Lato Bold | Stable outlines across computers; no installed-font dependency for the actual printed stamp. Curves are flattened to 0.008 mm. |
| Tkinter / ttk | Native windows with a canvas; small dependency footprint. Limited visual polish compared with Qt, adequate for a focused export decision. |
| TOML | Hand-editable configuration with an explicit precedence chain and strict validation. |
| filelock + atomic JSON journal | One local counter with recoverable G-code/log commits. SQLite alone cannot atomically commit a separate G-code file. A small journal makes that failure boundary explicit. |
| CSV | Portable audit records that a lab lead can inspect in a spreadsheet. Written via atomic replacement to avoid partial rows. |
| PyInstaller | Native Windows/macOS/Linux builds. Console mode retains stderr for PrusaSlicer errors; a console may briefly appear on Windows. Windows uses a one-folder build (`scripts/basemark-windows.spec`) because one-file extraction added ~10 s to every export; other platforms ship one file. |
| pytest + real slicer fixtures | Compare motion and E conservation; test skips, interrupted writes, locking, configuration and the actual Tk interaction model. |
| uv lockfile | Dependency versions and wheel hashes fixed for CI. This does not make OS-native binaries bit-reproducible. |

Rust would offer fast parsing and a small runtime, but implementing and distributing the
font/geometry/UI stack would cost substantially more for this pilot. Qt/PySide would be
reasonable if the application grows into a multi-pane lab manager; it is unnecessary for
two focused dialogs. Electron/Tauri or a web service would introduce a separate runtime or
local-server boundary without improving the slicer hook.

## Motion model

The parser interprets **the complete file** and rejects uncertain commands; the export path
only retains move records for the stamped layers plus the roof. This reduces memory and
allocation cost without trusting an unvalidated tail. It tracks XYZ modes, E modes, resets,
features, wipe regions, layer Z and extrusion widths. Known pre-layer purge moves are preserved.

The original spec's cumulative absolute-E subtraction conflicts with byte-identical upper
layers. BaseMark instead emits split moves and then `G92 E<original endpoint>` for each
modified absolute-E move. That command resets a logical coordinate; it does not push filament.
Later original commands, including retracts and E-mode switches, remain unchanged.

`G90/G91` invalidate our knowledge of E mode until explicit `M82/M83`. Prusa MK3 firmware
leaves E mode intact, whereas other firmware versions/dialects have different behavior.
Requiring an explicit mode prevents a cross-firmware assumption.

Arcs and firmware retraction currently skip the file. Linearization would need tolerances,
plane selection, full-circle/radius handling and new tests. It is deliberately deferred.

## Geometry and physical limits

Only annotated part extrusions contribute to the footprint. Skirt/brim/support/wipe/purge
paths are excluded. Largest deposited island selection is conservative: islands joined only
above the first layer still get one label total. The full stamp rectangle must fit the margin
and solid deposited coverage through depth N plus a roof in layer N+1.

Text outlines are mirrored in machine X. The UI mirrors the **entire scene** into an underside
view, so holes, dragging and text stay in agreement. Rotations happen in machine coordinates.

The auto-placer searches the pole of inaccessibility, centroid, representative points and a
bounded grid; it ranks valid positions by rectangle-to-boundary clearance. It is a heuristic,
not a proof of globally optimal placement. It shrinks in 0.5 mm steps, with the exact minimum
as a final candidate. A difficult concave surface may be skipped even if some placement exists.

The removed geometry follows extrusion **centerlines**. A physical bead has width and residual
pressure; it will not perfectly match the vector glyph. Layer N+1 retains its original speed,
fan and bridge strategy. Font thickness can grow beyond an easy bridging span at large sizes.
These are reasons to measure physical results, not claims that a nominal six-millimeter font
guarantees readability or negligible mechanical change.

## Failure and identity model

Before replacement: read the file, validate settings/profile, parse, find a fit, allow the
operator to decide, generate output, and check that input bytes have not changed. Then:

1. Hold a per-counter OS lock. After placement, acquire the CSV lock, validate its structure
   and check that the proposed ID is unused. Persist a journal with old/new hashes, ID and CSV record.
2. Write a same-directory temporary G-code file, flush/fsync, and atomically replace the input.
3. Write the CSV atomically, advance the counter, and clear the journal. Hold the CSV lock
   from the unused-ID check through the commit; nested recovery reuses that same lock object.

The counter increments after file replacement. Recovery checks hashes to distinguish an
uncommitted replacement from a committed one. If the slicer has already deleted a temporary
file, the operator must reconcile it; an uncertain ID is never automatically reused. A failure
after replacement is reported as **stamped, audit pending**, not “unchanged.”

Holding the counter lock while a popup is open prevents concurrent previews from showing
the same ID. Another export using that counter skips promptly instead of blocking indefinitely.
Assign one prefix per PC. Network filesystem locking/rename guarantees are not qualified.

## Source checks

- [Prusa post-processing documentation](https://help.prusa3d.com/article/post-processing-scripts_283913):
  temporary file path, uppercase environment, final filename and preview limitations.
- [Prusa firmware source](https://github.com/prusa3d/Prusa-Firmware/blob/MK3/Firmware/Marlin_main.cpp):
  G90/G91 and M82/M83 behavior; coordinate reset semantics.
- [Shapely manual](https://shapely.readthedocs.io/en/stable/manual.html): buffer, union, containment, polylabel.
- [fontTools BasePen](https://fonttools.readthedocs.io/en/latest/pens/basePen.html): outline traversal.
- [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html): native platform builds and one-file behavior.
- [GitHub runner images](https://github.com/actions/runner-images): supported release-build targets.

These decisions were checked against available documentation during implementation. The
actual hook was also exercised using PrusaSlicer 2.8.1; the lab's installed version remains to
be recorded. No “first ever” or novelty claim is made without a separate prior-art review.
