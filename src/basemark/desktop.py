"""Windowed Windows entry point. The slicer always uses the console basemark.exe."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import config_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BaseMark desktop settings")
    parser.add_argument("--config", type=Path, default=config_dir() / "config.toml")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.demo:
            from .popup import choose_placement
            from .service import demo_data

            footprint, surface, placed, settings = demo_data()
            choose_placement(footprint, surface, placed, settings, "PETG", "A042", demo=True)
        else:
            from .settings_ui import open_settings

            open_settings(args.config)
        return 0
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("BaseMark could not open", str(exc), parent=root)
        root.destroy()
        return 1
