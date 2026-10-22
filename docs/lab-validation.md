# Lab pilot: Windows → MK3S and Bambu plain G-code

Owner: Sebastians Krols, UBC IGEN 3D Print Shop.

## Before the first print

1. Record PrusaSlicer version, exact printer/model, firmware, nozzle, sheet and filament profile.
2. Keep the existing production profile; make a **BaseMark pilot** copy.
3. Disable binary G-code, arc fitting, vase mode and sequential printing. Use one material/tool.
4. Run the hook with `--dump-env` once. Review `%APPDATA%\BaseMark\environment.json` locally.
   Confirm filament type and width/height values. Use the normal command again afterwards.
5. Choose a unique PC prefix. Export the [80 × 40 × 2 mm coupon](../examples/basemark-coupon.stl)
   with the shop's actual profile and at least four solid bottom layers for a three-layer stamp.
6. Reopen the final exported file in PrusaSlicer's G-code Viewer. Check layers 1–N for the
   mirrored text gap, layer N+1 for an intact roof, and the purge/skirt/upper layers for changes.
7. Print an unstamped control and a 6 mm / 2-layer coupon first. Observe the early layers.

**Do not print regression G-code files from `tests/fixtures`.** Their startup sequences are
minimal software fixtures, without a qualified heating/homing procedure. Always slice the STL
with the lab's own printer profile.

## Physical matrix

Begin with the primary MK3S setup, then repeat accepted settings on each Bambu model/profile.
Use the shop's already approved sheet preparation and temperature procedures.

| Factor | Cases |
| --- | --- |
| Material / sheet | PLA / smooth PEI; PETG / textured PEI |
| Depth | 1, 2, 3 layers |
| Cap height | 4, 6, 8 mm |
| Nozzle | Start with the shop's 0.4 mm nozzle |
| Shape | Coupon; narrow tab; holed part; several objects; small part that should skip |
| Comparison | Unstamped control for each material/sheet |
| Partial print | Deliberately stopped coupon after its stamped base has formed |

This is 18 basic stamped combinations per printer family (2 materials × 3 depths × 3 sizes).
The bundled font is bold. Regular-font comparison remains a later experiment; this release
does not expose a font picker or claim to have run that comparison.

For each specimen, record:

- Label and CSV ID agree; material matches the spool actually loaded.
- Readability under ordinary shop lighting by two people who have not seen the job name.
- Glyph counters (`P`, `A`, `0`, `4`) remain distinguishable; text reads correctly from below.
- Roof quality, droop, ooze, debris and any visible change on the top face.
- Adhesion/lifting around the label compared with the unstamped control.
- Effect on thin walls, sealing or mating faces; use **Skip label** when inappropriate.
- Export time on the Windows PC, including one-file executable startup/antivirus overhead.

Use [lab-results.csv](../examples/lab-results.csv) as a collection sheet. Photograph the bottom
beside its recorded ID, plus the unstamped control. Do not substitute renderings for test photos.

## Acceptance gate for routine shop use

Choose one conservative preset per material/sheet only after it is consistently readable and
shows no unacceptable change relative to the control. Collect an initial set of ordinary jobs
with manager review enabled. Log every safe skip and its cause. Keep automatic mode opt-in
until the operators trust the placement behavior on their normal shapes.

Bambu acceptance requires its **specific** PrusaSlicer profile, plain `.gcode` export path and
printer transfer method to succeed. A file using Bambu-only commands may safely skip; “plain
G-code” alone is not evidence that its dialect is supported. `.gcode.3mf` packaging is excluded.

The remaining shop-specific questions are exact Windows/slicer versions, Bambu model/profile,
number of slicing computers and prefix assignments. No physical test result is implied here.
