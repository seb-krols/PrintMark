# From lab pilot to a useful shared tool

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

- Per-object labels and preview selection, including disconnected islands of one object.
- Arc linearization with bounded error and firmware-aware E behavior.
- Qualified OrcaSlicer dialect support and Bambu transfer/packaging research.
- Better bead-width compensation and slicer-generated roof bridging.
- A native upstream slicer implementation using its text/negative-volume tools, allowing
  material-aware labels before toolpath generation and a true 3D preview.

MIT is the chosen project license for easy reuse. Commercial positioning, naming and any
institutional ownership questions should be settled by the owner before public branding.
