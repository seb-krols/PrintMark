from __future__ import annotations

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


def center(root, width, height):
    root.update_idletasks()
    width = min(width, root.winfo_screenwidth() - 50)
    height = min(height, root.winfo_screenheight() - 80)
    x = (root.winfo_screenwidth() - width) // 2
    y = (root.winfo_screenheight() - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")


def brand(parent, eyebrow, title, subtitle):
    frame = ttk.Frame(parent)
    frame.pack(fill="x", padx=28, pady=(24, 18))
    ttk.Label(
        frame, text=f"B / BASEMARK     {eyebrow}", foreground=ACCENT, font=(FONT, 10, "bold")
    ).pack(anchor="w")
    ttk.Label(frame, text=title, style="Title.TLabel").pack(anchor="w", pady=(9, 4))
    ttk.Label(frame, text=subtitle, style="Muted.TLabel").pack(anchor="w")
    return frame


def divider(parent):
    tk.Frame(parent, background=LINE, height=1).pack(fill="x")
