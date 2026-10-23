# Changes

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
- Windows build scripts work in Windows PowerShell 5.1 and with per-user Inno Setup installs;
  the install test also runs outside GitHub Actions.
- 132 local tests pass. A native Windows build, install/upgrade/uninstall test and real
  PrusaSlicer 2.7.4 exports with the stock MK3S profiles passed on 2026-10-22. Physical
  printer qualification remains pending.

## 0.2.0 — initial repository pilot

- Conservative PrusaSlicer G-code parsing, mirrored text subtraction, placement UI, settings,
  local counters, CSV records and interrupted-export recovery.
- Windows installer/portable build scripts, cross-platform CI, installation guide and coupon.
- Export diagnostics and a compatibility check that does not consume an ID.
