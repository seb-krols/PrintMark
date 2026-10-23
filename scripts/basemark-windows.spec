# PyInstaller spec: Windows one-folder build with both executables sharing one runtime.
# One-file builds unpack ~70 MB to %TEMP% on every PrusaSlicer export (~10 s on lab PCs);
# a folder install starts in well under a second. Build: pyinstaller basemark-windows.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = collect_data_files("basemark")


def analysis(script):
    return Analysis([str(root / "scripts" / script)], pathex=[str(root / "src")], datas=datas)


cli = analysis("entrypoint.py")
desktop = analysis("desktop_entrypoint.py")


def executable(a, name, console):
    return EXE(
        PYZ(a.pure),
        a.scripts,
        exclude_binaries=True,
        name=name,
        console=console,
        upx=False,
    )


# Console mode keeps stderr visible to PrusaSlicer; the settings app is windowed.
COLLECT(
    executable(cli, "basemark", console=True),
    cli.binaries,
    cli.datas,
    executable(desktop, "basemark-desktop", console=False),
    desktop.binaries,
    desktop.datas,
    name="basemark",
    upx=False,
)
