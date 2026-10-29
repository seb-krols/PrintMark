# From lab pilot to a useful shared tool

## Done so far

- v0.3: find a part by its printed number; try 90° before shrinking; check the log before
  changing G-code.
- v0.4–0.5: one-page Windows installer that connects PrusaSlicer; the BaseMark app (Overview,
  Stamp, Find part, Advanced); corner notices after each export; faster parsing.
- v0.6: material-only labels by default (`PLA`), optional part numbers, 3 mm text, an explicit
  Save button, no computer prefix.
- v0.7: a label on every part of a plate; a background warning for exports made without
  BaseMark; README for shop staff.

Next: physical test prints at 3 mm and 2.5 mm (PLA, PETG) to confirm the defaults, then arc
fitting and binary G-code support, so stock Prusa presets work without `+ BaseMark` copies.

## Pilot

- Qualify MK3S PLA/smooth and PETG/textured settings with the supplied matrix.
- Capture the actual Windows environment and Bambu profile outputs; turn compatibility fixes
  into regression fixtures, with permission to redistribute any model/profile data.
- Measure Windows cold-start time and confirm the portable exe runs without Python installed.
- Collect real underside photos, failed-print examples, skip reasons and operator feedback.

## First public release

- Review the private `seb-krols/PrintMark` repository and inspect native build artifacts.
  The supplied release workflow creates draft releases, not automatic public launches.
- Add verified physical results and a short recording of a real placement/export interaction.
- Keep release notes explicit about tested slicer/printer combinations and known safe skips.
- Add signing/notarization when distribution scale warrants it.
- Review existing projects and discussions before making novelty claims. Publish measured
  recycling/identification improvements instead of asserting that no similar tool exists.

Possible places to share results: Printables, Prusa's forum and relevant slicer feature
discussions, then other communities that allow project posts. No posts or messages are sent
by this implementation task.

## Adoption and paid services

Keep the offline marking engine open and useful. Plausible paid work includes installation,
profile qualification, staff onboarding, maintenance/support and deployment for larger labs.
Measure whether other labs actually need these services before building billing or a cloud app.

A later optional shared registry could provide globally unique part IDs, jobs, reprints and
material provenance. It needs offline reservations, authentication, backups and conflict
handling; a shared `counter.json` on a network drive is not an adequate substitute.

## Technical follow-ups

- Labels for parts that are disconnected on the first layer but belong to one object
  (today: largest island per labelled object).
- Arc linearization with bounded error and firmware-aware E behavior.
- Qualified OrcaSlicer dialect support and Bambu transfer/packaging research.
- Better bead-width compensation and slicer-generated roof bridging.
- A native upstream slicer implementation using its text/negative-volume tools, allowing
  material-aware labels before toolpath generation and a true 3D preview.

Since 0.8.0 BaseMark is licensed under PolyForm Noncommercial 1.0.0: free for noncommercial
use, commercial use by separate paid license, with a free monthly allowance of 100 stamps
unlocked by signed keys ([LICENSING.md](../LICENSING.md)). Still to settle before selling
licenses: a written commercial license agreement and prices, and any institutional ownership
questions (the project started at UBC IGEN) with UBC's innovation office.
