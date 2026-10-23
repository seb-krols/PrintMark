from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

BG = "#f5f3ee"
PANEL = "#ffffff"
INK = "#1d302b"
MUTED = "#6c7871"
ACCENT = "#137d6b"
LINE = "#dce1da"
DANGER = "#b84a39"
FONT = "Segoe UI"


def style(root):
    root.configure(bg=BG)
    theme = ttk.Style(root)
    theme.theme_use("clam")
    theme.configure("TFrame", background=BG)
    theme.configure("Panel.TFrame", background=PANEL)
    theme.configure("TLabel", background=BG, foreground=INK, font=(FONT, 10))
    theme.configure("Muted.TLabel", foreground=MUTED)
    theme.configure("Title.TLabel", font=(FONT, 24, "bold"))
    theme.configure("Heading.TLabel", font=(FONT, 12, "bold"))
    theme.configure(
        "TButton",
        font=(FONT, 10),
        padding=(14, 10),
        background=PANEL,
        foreground=INK,
        borderwidth=1,
        bordercolor=LINE,
    )
    theme.map("TButton", background=[("active", "#e8ece6")])
    theme.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0)
    theme.map("Accent.TButton", background=[("active", "#0b6656"), ("disabled", "#b6c6be")])
    theme.configure("TEntry", padding=8, fieldbackground=PANEL, foreground=INK)
    theme.configure("TCombobox", padding=7, fieldbackground=PANEL, foreground=INK)
    theme.configure("TCheckbutton", background=BG, foreground=INK, font=(FONT, 10))
    theme.configure("TNotebook", background=BG, borderwidth=0)
    theme.configure("TNotebook.Tab", padding=(20, 10), font=(FONT, 10))


def work_area(root):
    """Usable screen (x, y, width, height) without the taskbar, in Tk's pixel units."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except (AttributeError, OSError):
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def compact(root):
    # Laptops at 150–200% scaling offer ~650–720 px of height: shrink the header there.
    return work_area(root)[3] < 820


def center(root, width, height):
    root.update_idletasks()
    left, top, area_width, area_height = work_area(root)
    frame = 40  # title bar and borders sit outside the Tk geometry
    width = min(width, area_width - 20)
    height = min(height, area_height - frame)
    min_width, min_height = root.minsize()
    root.minsize(min(min_width, width), min(min_height, height))
    x = left + (area_width - width) // 2
    y = top + max(0, (area_height - frame - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def brand(parent, eyebrow, title, subtitle):
    small = compact(parent)
    frame = ttk.Frame(parent)
    frame.pack(fill="x", padx=28, pady=(12, 8) if small else (24, 18))
    ttk.Label(
        frame, text=f"B / BASEMARK     {eyebrow}", foreground=ACCENT, font=(FONT, 10, "bold")
    ).pack(anchor="w")
    title_font = (FONT, 17, "bold") if small else (FONT, 24, "bold")
    ttk.Label(frame, text=title, style="Title.TLabel", font=title_font).pack(
        anchor="w", pady=(4, 2) if small else (9, 4)
    )
    if not small:
        ttk.Label(frame, text=subtitle, style="Muted.TLabel").pack(anchor="w")
    return frame


def divider(parent):
    tk.Frame(parent, background=LINE, height=1).pack(fill="x")
