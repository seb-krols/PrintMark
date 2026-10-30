# Third-party notices

BaseMark's original code is licensed under the PolyForm Noncommercial License 1.0.0 (see
[LICENSE.md](LICENSE.md) and [LICENSING.md](LICENSING.md)). Third-party components keep their own
licenses, which are unaffected.

| Component | License | Use |
| --- | --- | --- |
| Python | PSF license | Runtime in standalone executables |
| Shapely | BSD 3-Clause | Polygon and line operations |
| GEOS | LGPL 2.1 | Shared geometry library distributed by Shapely wheels |
| NumPy | BSD 3-Clause | Shapely's array dependency |
| fontTools | MIT | Font outlines |
| Lato Bold | SIL Open Font License 1.1 | Unmodified bundled font |
| Tcl/Tk | Tcl/Tk BSD-style licenses | Desktop windows |
| tomli-w | MIT | TOML settings writes |
| Pillow | MIT-CMU (HPND) | Smooth placement preview |
| filelock | MIT (locked version) | Local inter-process locking |
| PyInstaller | GPL with bootloader distribution exception | Packaging |

Font source: [Google Fonts Lato directory](https://github.com/google/fonts/tree/main/ofl/lato).
The complete font license is bundled beside the font and in release archives as `OFL.txt`.
See `uv.lock` for the exact dependency versions and wheel hashes used by the builds.

Release archives collect installed dependency license texts, including GEOS and NumPy's
bundled-library notices, plus Python and Tcl/Tk notices from `licenses/`. Source links for
those runtime texts: [Python](https://github.com/python/cpython/blob/3.12/LICENSE),
[Tcl](https://github.com/tcltk/tcl/blob/core-8-6-branch/license.terms),
[Tk](https://github.com/tcltk/tk/blob/core-8-6-branch/license.terms).
The Linux development executable may use Tk 9; release CI uses setup-python's platform Tk.
Review exact runtime contents when changing the build configuration or creating installers.
