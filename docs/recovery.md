# Counter and audit recovery

Normal skips, cancelled popups and failed replacements do not consume an ID. A JSON journal
handles the interval between replacing G-code and committing its counter/CSV record.

Close any placement/settings window before inspecting state. Keep a backup of `counter.json`,
`log.csv` and any surviving exported G-code. Do not delete a pending journal just to clear an error.

## Automatic recovery

On the next run, BaseMark acquires the counter lock and inspects `pending` in `counter.json`:

- Input hash equals `before`: replacement did not happen; clear pending, retain the next ID.
- Input hash equals `after`: stamping happened; append the CSV record once, advance the ID.
- Missing temporary file, but a recorded absolute final path matches `after`: finish the audit.
- Missing file without a matching final export, or either hash differs: stop stamping with a
  warning; retain pending for review.

A missing temporary file is possible because PrusaSlicer copies its result to the final export
destination and then removes the temporary file. The journal retains the final name inside
`pending.row.gcode_filename`, the output hash and the proposed CSV row.

## Missing temporary file / unresolved transaction

Open **Settings → Diagnostics → Recover from exported G-code** and select the surviving
stamped export. BaseMark requires an exact SHA-256 match, then records the original result
and advances the counter without modifying the selected file. A mismatch preserves the journal.
The CLI equivalent is `basemark --recover-from "path/to/final.gcode"` (plus `--config` if used).

Opening settings and performing a dry-run/check do not automatically commit pending audits.
Normal stamping runs still recover a known transaction before assigning another ID.

If the result cannot be established, preserve the journal backup and retire the uncertain ID:
set `next` to at least `pending.next`, then set `pending` to `null`. Keep a separate written
audit note explaining the retired ID. Do not fabricate a successful stamp row in the CSV.
This deliberately allows a gap in numbering rather than possible duplicate identity.

For a read-only or locked CSV, close the spreadsheet or correct file permissions and retry.
An existing CSV with incompatible columns must be preserved/renamed and a fresh log created
at the journal's log path before recovery. Keep both logs together as an audit history.

Never move a live counter between computers or put it on a network share in this release.
For a fresh numbering series, choose a new prefix and a new local counter file.
