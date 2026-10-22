# Install BaseMark on Windows

BaseMark is the application in the **PrintMark** repository. This pilot targets Windows x64,
PrusaSlicer and plain text G-code for the shop's MK3S and Bambu profiles. Python is not needed.
Printer/profile qualification and physical coupon tests are still required.

**Build status (2026-10-22):** GitHub currently fails before starting the Windows runner.
The installer source is ready, but there is no successful downloadable Windows artifact yet.
The steps below apply once the build is unblocked; the source-build command at the end can
also run on a Windows PC. See the [verification record](docs/verification.md).

## 1. Download and install

While signed into the GitHub account with access to this private repository, open
[Windows installer builds](https://github.com/seb-krols/PrintMark/actions/workflows/windows.yml).
Choose the latest **successful** run on `main`, then download the `basemark-windows-x64`
artifact at the bottom. Extract that artifact ZIP. It contains:

- `basemark-0.3.0-windows-x64-setup.exe`: the recommended per-user installer.
- `basemark-0.3.0-windows-x64.zip`: portable alternative; extract to a permanent local folder.
- SHA-256 files for verifying downloads with PowerShell `Get-FileHash`.

Run the setup executable. It installs to `%LOCALAPPDATA%\Programs\BaseMark` without
administrator rights and adds **BaseMark Settings** to the Start menu. Builds are currently
unsigned; Windows may show a publisher warning. Check the download source and checksum.
If your institution blocks unsigned software, ask its IT administrator about deployment.

Future reviewed versions will appear in [Releases](https://github.com/seb-krols/PrintMark/releases).
Private repository artifacts require GitHub access and expire; keep the tested lab build locally.

## 2. Connect PrusaSlicer

1. Open **BaseMark Settings** from Start (or `basemark-desktop.exe` in the portable folder).
2. Under **Identity & records**, choose a unique PC prefix: `A`, `B`, etc. Save settings.
3. Open **PrusaSlicer setup** and click **Copy command**. This copies the actual installed
   path to `basemark.exe`, including quotes. Use this executable for the slicer hook.
4. In PrusaSlicer, enable **Expert mode**, then open **Print Settings → Output options →
   Post-processing scripts**. Paste the command on its own line. Save a copy of the lab's
   print preset with a recognizable name, such as `Lab PLA + BaseMark`.
5. Use **plain text G-code** and disable **arc fitting**. The first release skips binary
   `.bgcode`, packaged `.gcode.3mf` and arc moves. Use a single filament/tool and at least
   three solid bottom layers for the default two-layer stamp and its roof.

Example only—use the path copied from your own installation:

```text
"C:\Users\Seb\AppData\Local\Programs\BaseMark\basemark.exe"
```

PrusaSlicer supplies the temporary G-code filename automatically. Do not add a filename
yourself. Each saved **print preset** needs the hook; installing BaseMark does not alter
PrusaSlicer profiles. Add `--mode auto` after the quoted executable to skip placement prompts.
Filament Notes can contain `basemark: layers=2; size=6` for profile-specific settings.

## 3. Check and print a coupon

1. Import `examples\basemark-coupon.stl` from the install folder into PrusaSlicer. Use your
   actual printer, filament and sheet presets. Export once **without the hook** to keep an
   original reference; then restore the hook.
2. In BaseMark **Diagnostics → Check G-code**, select that original export. The check uses
   saved settings and embedded slicer metadata, leaves the file unchanged and consumes no ID.
   It verifies software compatibility and fit; it does not validate printer behavior.
3. Export with the hook enabled. Confirm the material and ID in the popup, drag if needed,
   and apply. Open **Diagnostics → Refresh result** to see whether the export stamped or
   skipped. `last-export.json` also records the latest result.
4. Open the **final exported file** in PrusaSlicer's G-code Viewer. Check the text-shaped
   gaps in the first two layers and the solid roof above. The slicer's normal preview shows
   the original toolpaths before post-processing.
5. Print the coupon under normal shop supervision. Start with MK3S PLA/smooth, then
   PETG/textured; qualify each Bambu profile separately. Follow the
   [physical test matrix](docs/lab-validation.md) before enabling routine jobs.

For Bambu, the printer's existing transfer method must already accept the PrusaSlicer
plain G-code output. BaseMark does not provide printer transfer or `.gcode.3mf` packaging.

## Daily use, updates and removal

- **Find a part:** open **Find part** in settings and enter its full printed ID (`A042`).
  It searches the CSV selected in saved settings and shows the original export's details.
  An unknown ID may belong to another PC; each computer keeps its own local history.
- **Skip one job:** choose **Skip label** in the popup. For automatic mode, temporarily
  append `--off` to the hook. Remove that option afterward.
- **Settings and records:** `%APPDATA%\BaseMark\` contains `config.toml`, `counter.json`,
  `log.csv` and `last-export.json`. Back up this folder with the shop's records.
- **Upgrade:** close BaseMark/export windows and run the newer installer. It keeps the
  installation path, settings and ID history. Keep a copy of the last qualified installer.
- **Uninstall:** first remove the hook from every affected PrusaSlicer preset, then uninstall
  BaseMark in Windows Settings. Uninstall deliberately preserves AppData records.
- **Move to another PC:** install normally and assign a different prefix. Do not share a
  live counter over a network drive or silently reuse another PC's numbering series.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No popup or marking | Check the selected print preset, master switch and Diagnostics result. A safe skip leaves the export unchanged. |
| File cannot fit a stamp | Use a larger footprint, adjust size/margin within limits, or skip this part. Holes and sparse bottoms reduce the usable area. |
| Unsupported command/profile | Run `--dump-env` through the hook once, preserve a small original export and report the skip reason. Restore the normal hook afterward. |
| Pending audit / missing temporary file | Close Excel if it has the CSV open. Use **Diagnostics → Recover from exported G-code** with the exact surviving stamped file. See [recovery](docs/recovery.md). |
| ID already exists in the audit log | Restore the counter backup, or move Next ID above the highest recorded number for this series. Keep the CSV; do not delete history to clear the error. |
| Export fails to launch BaseMark | Re-copy the quoted command from settings; ensure the exe has not been moved or removed. |

For a command-line compatibility check in PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\BaseMark\basemark.exe" --check "C:\Jobs\original.gcode"
```

Exit 0 means the check completed without a compatibility error; read its message (a disabled
stamp is reported as disabled). Exit 2 means the job cannot currently be stamped. Normal
post-processing skips still exit 0 so labeling does not block a print export.

`--dump-env` writes relevant slicer settings to `%APPDATA%\BaseMark\environment.json`
and skips marking that export. Review diagnostics before sharing: paths, filenames and
material settings can identify jobs. `--dump-all-env` may include credentials.

## Build Windows packages from source

Install Python 3.12, [uv](https://docs.astral.sh/uv/) and
[Inno Setup 6](https://jrsoftware.org/isinfo.php) on Windows. From the checkout root:

```powershell
.\scripts\build_windows.ps1
```

This runs tests, builds both standalone executables, verifies frozen stamping, packages
licenses/docs and compiles the installer into `dist\`. The GitHub workflow additionally
checks installation to a path with spaces/non-ASCII characters, app launch, upgrade and
uninstall with counter/log preservation. PyInstaller builds must run on their target OS.

For macOS/Linux source or portable use, see [README](README.md).
