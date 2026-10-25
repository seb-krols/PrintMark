# Install BaseMark on Windows

BaseMark is the application in the **PrintMark** repository. This pilot targets Windows x64,
PrusaSlicer and plain text G-code for the shop's MK3S and Bambu profiles. Python is not needed.
Printer/profile qualification and physical coupon tests are still required.

**Build status (2026-10-23):** the Windows installer is built and tested on a native Windows 11
PC: install, upgrade and uninstall checks pass, and real PrusaSlicer 2.7.4 and 2.9.6 exports
with stock Prusa profiles (MK4S, MK4, CORE One, MK3.9, XL, MINI, MK3S) were stamped. GitHub
Actions still fails before starting its runner, so pilot installers are built locally and
attached to [Releases](https://github.com/seb-krols/PrintMark/releases). See the
[verification record](docs/verification.md).

## 1. Download and install

While signed into the GitHub account with access to this private repository, open
[Releases](https://github.com/seb-krols/PrintMark/releases) and pick the newest
**Windows pilot**. (Once GitHub Actions runs again, every successful
[Windows installer build](https://github.com/seb-krols/PrintMark/actions/workflows/windows.yml)
also has a `basemark-windows-x64` artifact with the same files.) The downloads are:

- `basemark-0.5.0-windows-x64-setup.exe`: the recommended per-user installer.
- `basemark-0.5.0-windows-x64.zip`: portable alternative; extract to a permanent local folder.
  Keep `basemark.exe`, `basemark-desktop.exe` and the `_internal` folder together.
- SHA-256 files for verifying downloads with PowerShell `Get-FileHash`.

Select your usual printer and print presets in PrusaSlicer and close it, then run the
setup executable. Its single page asks for this PC's **prefix** and offers **Connect
PrusaSlicer now** (does the automatic setup below). It installs to
`%LOCALAPPDATA%\Programs\BaseMark` without administrator rights and adds **BaseMark**
to the Start menu. For several PCs, install silently with each PC's prefix:
`setup.exe /VERYSILENT /PREFIX=B` (`/CONNECT=no` skips PrusaSlicer). The installer
never changes an already working PrusaSlicer setup. Builds are currently
unsigned; SmartScreen may say *Windows protected your PC*: choose **More info → Run anyway**
after checking the download source and checksum.
If your institution blocks unsigned software, ask its IT administrator about deployment.

Future reviewed versions will appear in [Releases](https://github.com/seb-krols/PrintMark/releases).
Private repository artifacts require GitHub access and expire; keep the tested lab build locally.

## 2. Connect PrusaSlicer

1. Open **BaseMark** from Start (or `basemark-desktop.exe` in the portable folder).
2. On **Overview**, enter a unique PC prefix: `A`, `B`, etc. Changes save automatically.

**Automatic (recommended):** in PrusaSlicer select the printer and print presets you use,
close PrusaSlicer, then on BaseMark's **Overview** click **Set up PrusaSlicer**. BaseMark
writes `… + BaseMark` copies of both presets into PrusaSlicer's settings folder (hook added,
arc fitting off, binary G-code off), fully resolved from their parents, and selects them.
Existing presets are untouched; `PrusaSlicer.ini.basemark-backup` keeps the previous
selection. Repeat for each print preset the lab uses. **Check again** on the Overview lists
what the saved presets still lack. On the command line: `basemark.exe --setup-prusaslicer` and
`basemark.exe --check-prusaslicer` (exit 0 ready, 2 needs fixing).

**Manual:**

3. Open **Advanced → PrusaSlicer hook** and click **Copy**. This copies the actual installed
   path to `basemark.exe`, including quotes. Use this executable for the slicer hook.
4. In PrusaSlicer, enable **Expert mode**, then open **Print Settings → Output options →
   Post-processing scripts**. Paste the command on its own line. Save a copy of the lab's
   print preset with a recognizable name, such as `Lab PLA + BaseMark`.
5. Use **plain text G-code** and disable **arc fitting**: **Print Settings → Advanced → Arc
   fitting: Disabled**, and for Prusa MK4/MK4S/MK3.9/CORE One/XL/MINI printers untick
   **Printer Settings → General → Firmware → Supports binary G-code** (on by default there);
   save that printer preset under a new name too. The first release skips binary
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
2. In BaseMark **Advanced → Check a G-code file**, select that original export. The check uses
   saved settings and embedded slicer metadata, leaves the file unchanged and consumes no ID.
   It verifies software compatibility and fit; it does not validate printer behavior.
3. Export with the hook enabled. Confirm the material and ID in the popup, drag if needed,
   and apply. BaseMark's Overview shows under *Recent exports* whether it stamped or
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

- **Find a part:** open **Find part** in BaseMark and enter its full printed ID (`A042`).
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
| No popup or marking | Click **Check again** on BaseMark's Overview. Usually the print preset with the hook was never saved, a different preset or `.3mf` project preset is active, or the job was only sliced, not exported. If Recent exports shows *skipped*, the reason is listed; a safe skip leaves the export unchanged. |
| File cannot fit a stamp | Use a larger footprint, adjust size/margin within limits, or skip this part. Holes and sparse bottoms reduce the usable area. |
| Unsupported command/profile | Run `--dump-env` through the hook once, preserve a small original export and report the skip reason. Restore the normal hook afterward. |
| Pending audit / missing temporary file | Close Excel if it has the CSV open. Use **Advanced → Recover an interrupted export** with the exact surviving stamped file. See [recovery](docs/recovery.md). |
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

Install [uv](https://docs.astral.sh/uv/) and [Inno Setup 6](https://jrsoftware.org/isinfo.php)
on Windows; neither needs administrator rights. uv downloads Python 3.12 itself:

```powershell
winget install --id astral-sh.uv -e --scope user
winget install --id JRSoftware.InnoSetup -e --scope user
uv python install 3.12
```

From the checkout root, in Windows PowerShell or PowerShell 7:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test_windows_install.ps1
```

The first command runs lint and tests, builds the one-folder app (`dist\basemark\`),
verifies frozen stamping and lookup, packages licenses/docs and compiles the installer into
`dist\`. The second installs to a temporary path with spaces/non-ASCII characters and checks
stamping, the settings window, upgrade and uninstall with counter/log preservation. It uses a
temporary `APPDATA`, so real settings and ID history are not touched. PyInstaller builds
must run on their target OS.

For macOS/Linux source or portable use, see [README](README.md).
