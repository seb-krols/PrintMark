# G-code fixture provenance

These are **actual PrusaSlicer outputs**, generated locally with PrusaSlicer
`2.8.1+linux-x64-GTK3-202409181416` from our original `examples/basemark-coupon.stl` and
the minimal regression profile `coupon.ini`.

| File | Coverage |
| --- | --- |
| `prusaslicer-2.8.1-pla-relative.gcode` | PLA metadata, M83, first-layer paths, skirts and upper layers |
| `prusaslicer-2.8.1-petg-relative.gcode` | PETG metadata and M83 |
| `prusaslicer-2.8.1-pla-absolute.gcode` | M82, coordinate restoration, retractions |

Regenerate with `python scripts/regenerate_fixtures.py /path/to/prusa-slicer`. Use the recorded
version; generated comments include timestamps and paths, so regenerating need not be byte-identical.
Synthetic programs in `tests/conftest.py` cover relative XYZ, malformed input, arc safe skips,
wipe exclusion and other edge cases. They are explicitly synthetic, not captured lab jobs.

**Do not print these files.** The minimal startup does not heat/home a real machine. They do
not certify MK3S or Bambu compatibility. The bundled official MK3S profile was separately
tested through the slicer hook during development, as recorded in `docs/verification.md`.

There is no Bambu lab fixture yet. Add one only after obtaining a real export from the owner's
specific PrusaSlicer profile and confirming redistribution rights for its model/profile data.
