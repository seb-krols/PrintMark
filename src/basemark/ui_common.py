"""Shared look and behaviour for BaseMark's Tk windows.

Sizes in this module are written in 96-DPI pixels and scaled with `px()`, because the
process is DPI aware on Windows: text stays crisp at 150–200% display scaling instead of
being bitmap-stretched by Windows.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#f6f7f5"  # window background
SIDEBAR = "#eceeea"
PANEL = "#ffffff"  # cards
LINE = "#dfe3de"
INK = "#17211e"
MUTED = "#5f6a65"
SUBTLE = "#8a938e"
ACCENT = "#0f7b67"
ACCENT_DARK = "#0a6352"
ACCENT_SOFT = "#e2f1ec"
WARN = "#a86412"
WARN_SOFT = "#fbf1e1"
DANGER = "#c0392b"
DANGER_SOFT = "#fbe8e5"
CANVAS = "#eef1ec"
BUTTON = "#f1f3f0"  # secondary buttons: visibly clickable on white cards
FIELD_LINE = "#cbd2ca"  # input and button borders
FONT = "Segoe UI"
SEMIBOLD = "Segoe UI Semibold"
MONO = "Consolas"

_scale = 1.0


def enable_dpi_awareness():
    """Call before creating the first Tk window."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
        except (AttributeError, OSError):
            pass


def px(value: float) -> int:
    return round(value * _scale)


def style(root):
    global _scale, FONT, SEMIBOLD, MONO
    _scale = max(1.0, root.winfo_fpixels("1i") / 96)
    families = set(tkfont.families(root))
    FONT = next(
        (f for f in ("Segoe UI", "Helvetica Neue", "Arial") if f in families), "TkDefaultFont"
    )
    SEMIBOLD = "Segoe UI Semibold" if "Segoe UI Semibold" in families else FONT
    MONO = next((f for f in ("Cascadia Mono", "Consolas", "Menlo") if f in families), "TkFixedFont")
    root.configure(bg=BG)
    theme = ttk.Style(root)
    theme.theme_use("clam")
    theme.configure(".", background=BG, foreground=INK, font=(FONT, 10), borderwidth=0)
    for name, background in [("", BG), ("Card.", PANEL), ("Side.", SIDEBAR)]:
        theme.configure(f"{name}TFrame", background=background)
        theme.configure(f"{name}TLabel", background=background, foreground=INK, font=(FONT, 10))
        theme.configure(f"{name}Muted.TLabel", background=background, foreground=MUTED)
        theme.configure(
            f"{name}Small.TLabel", background=background, foreground=MUTED, font=(FONT, 9)
        )
        theme.configure(
            f"{name}Heading.TLabel", background=background, foreground=INK, font=(SEMIBOLD, 12)
        )
        theme.configure(
            f"{name}Eyebrow.TLabel",
            background=background,
            foreground=SUBTLE,
            font=(SEMIBOLD, 8),
        )
    theme.configure("Title.TLabel", background=BG, foreground=INK, font=(SEMIBOLD, 18))
    theme.configure("Value.TLabel", background=PANEL, foreground=INK, font=(SEMIBOLD, 10))
    theme.configure("Big.TLabel", background=PANEL, foreground=INK, font=(SEMIBOLD, 22))
    theme.configure("Mono.TLabel", background=PANEL, foreground=MUTED, font=(MONO, 9))
    theme.configure(
        "TButton",
        font=(FONT, 10),
        padding=(px(14), px(7)),
        background=BUTTON,
        foreground=INK,
        bordercolor=FIELD_LINE,
        lightcolor=BUTTON,
        darkcolor=BUTTON,
        borderwidth=1,
        focuscolor=BUTTON,
        relief="flat",
    )
    theme.map(
        "TButton",
        background=[("disabled", BG), ("pressed", "#dfe4de"), ("active", "#e8ece7")],
        lightcolor=[("pressed", "#dfe4de"), ("active", "#e8ece7")],
        darkcolor=[("pressed", "#dfe4de"), ("active", "#e8ece7")],
        foreground=[("disabled", SUBTLE)],
        bordercolor=[("focus", ACCENT), ("active", "#b9c1b8")],
    )
    theme.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="white",
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        font=(SEMIBOLD, 10),
    )
    theme.map(
        "Accent.TButton",
        background=[("disabled", "#b9cbc5"), ("pressed", ACCENT_DARK), ("active", ACCENT_DARK)],
        bordercolor=[("disabled", "#b9cbc5"), ("active", ACCENT_DARK)],
        foreground=[("disabled", "white")],
    )
    theme.configure("Big.Accent.TButton", padding=(px(22), px(10)), font=(SEMIBOLD, 11))
    theme.configure("Big.TButton", padding=(px(18), px(10)), font=(FONT, 11))
    theme.configure(
        "Link.TButton",
        background=PANEL,
        foreground=ACCENT,
        bordercolor=PANEL,
        lightcolor=PANEL,
        darkcolor=PANEL,
        padding=(0, px(2)),
        font=(SEMIBOLD, 9),
    )
    theme.map("Link.TButton", foreground=[("active", ACCENT_DARK)], background=[("active", PANEL)])
    entry = dict(
        padding=(px(8), px(6)),
        fieldbackground=PANEL,
        foreground=INK,
        bordercolor=FIELD_LINE,
        lightcolor=PANEL,
        darkcolor=PANEL,
        insertcolor=INK,
    )
    theme.configure("TEntry", **entry)
    theme.map(
        "TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        fieldbackground=[("readonly", "#f3f5f2")],
    )
    theme.configure("TCombobox", arrowsize=px(12), **entry)
    theme.map("TCombobox", bordercolor=[("focus", ACCENT)], fieldbackground=[("readonly", PANEL)])
    theme.configure(
        "Vertical.TScrollbar",
        background="#d9ddd8",
        troughcolor=PANEL,
        bordercolor=PANEL,
        arrowcolor=MUTED,
        lightcolor="#d9ddd8",
        darkcolor="#d9ddd8",
        gripcount=0,
        arrowsize=px(12),
    )
    theme.configure("TSeparator", background=LINE)
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))


def card(parent, **pack):
    """A white panel with a hairline border."""
    frame = tk.Frame(parent, background=PANEL, highlightthickness=1, highlightbackground=LINE)
    inner = ttk.Frame(frame, style="Card.TFrame", padding=(px(18), px(16)))
    inner.pack(fill="both", expand=True)
    if pack:
        frame.pack(**pack)
    return frame, inner


def pill(parent, text, tone="ok", background=PANEL):
    colours = {
        "ok": (ACCENT, ACCENT_SOFT),
        "warn": (WARN, WARN_SOFT),
        "bad": (DANGER, DANGER_SOFT),
        "info": (MUTED, "#eef0ed"),
    }
    foreground, fill = colours[tone]
    return tk.Label(
        parent,
        text=text,
        foreground=foreground,
        background=fill,
        font=(SEMIBOLD, 9),
        padx=px(9),
        pady=px(2),
    )


def status_icon(parent, ok, background=PANEL):
    """✓ / ! / ✕ in the matching tone; `ok` is True, None (note) or False."""
    glyph, colour = {True: ("✓", ACCENT), None: ("!", WARN), False: ("✕", DANGER)}[ok]
    return tk.Label(
        parent, text=glyph, foreground=colour, background=background, font=(SEMIBOLD, 11)
    )


class Segmented(tk.Frame):
    """A row of mutually exclusive choices bound to a StringVar."""

    def __init__(self, parent, variable, choices, command=None, background=PANEL):
        super().__init__(parent, background=LINE, padx=1, pady=1)
        self.variable, self.command, self.buttons = variable, command, {}
        for value, label in choices:
            button = tk.Label(
                self,
                text=label,
                font=(FONT, 10),
                padx=px(14),
                pady=px(6),
                cursor="hand2",
            )
            button.pack(side="left", padx=(0, 1))
            button.bind("<Button-1>", lambda _e, v=value: self.select(v))
            self.buttons[value] = button
        variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def select(self, value):
        self.variable.set(value)
        if self.command:
            self.command()

    def refresh(self):
        for value, button in self.buttons.items():
            chosen = self.variable.get() == value
            button.configure(
                background=ACCENT if chosen else PANEL,
                foreground="white" if chosen else INK,
                font=(SEMIBOLD if chosen else FONT, 10),
            )


class Switch(tk.Canvas):
    """An on/off toggle bound to a BooleanVar."""

    def __init__(self, parent, variable, command=None, background=PANEL):
        self.w, self.h = px(40), px(22)
        super().__init__(
            parent,
            width=self.w,
            height=self.h,
            background=background,
            highlightthickness=0,
            cursor="hand2",
        )
        self.variable, self.command = variable, command
        self.bind("<Button-1>", lambda _e: self.toggle())
        variable.trace_add("write", lambda *_: self.draw())
        self.draw()

    def toggle(self):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self):
        self.delete("all")
        on, w, h, r = bool(self.variable.get()), self.w, self.h, self.h / 2
        fill = ACCENT if on else "#c5cbc6"
        self.create_oval(0, 0, h, h, fill=fill, outline=fill)
        self.create_oval(w - h, 0, w, h, fill=fill, outline=fill)
        self.create_rectangle(r, 0, w - r, h, fill=fill, outline=fill)
        knob = px(3)
        x = w - h + knob if on else knob
        self.create_oval(x, knob, x + h - 2 * knob, h - knob, fill="white", outline="white")


class ScrollPage(ttk.Frame):
    """A vertically scrolling page; `self.body` holds the content."""

    def __init__(self, parent, padding=(28, 22, 28, 22)):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=BG, highlightthickness=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=tuple(px(p) for p in padding))
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.fit())
        self.canvas.bind("<Configure>", lambda e: self.fit(e.width))
        self.canvas.bind("<Enter>", lambda _e: self.bind_all("<MouseWheel>", self.wheel))
        self.canvas.bind("<Leave>", lambda _e: self.unbind_all("<MouseWheel>"))

    def fit(self, width=None):
        if width:
            self.canvas.itemconfigure(self.window, width=width)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        needed = self.body.winfo_reqheight() > self.canvas.winfo_height()
        if needed and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        elif not needed and self.bar.winfo_ismapped():
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def wheel(self, event):
        if self.bar.winfo_ismapped():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


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


def center(root, width, height):
    """Open at `width`×`height` (96-DPI px), shrunk to fit above the taskbar."""
    root.update_idletasks()
    left, top, area_width, area_height = work_area(root)
    frame = px(40)  # title bar and borders sit outside the Tk geometry
    width = min(px(width), area_width - px(20))
    height = min(px(height), area_height - frame)
    min_width, min_height = root.minsize()
    root.minsize(min(min_width, width), min(min_height, height))
    x = left + (area_width - width) // 2
    y = top + max(0, (area_height - frame - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def keep_visible(root, interval_ms=1500):
    """Keep a blocking window on screen: PrusaSlicer waits until the operator decides.

    When PrusaSlicer launches BaseMark, Windows sometimes leaves the window minimized (seen at
    startup and while waiting), which looks like a hung export. Restore it instead.
    """

    def restore():
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        if sys.platform == "win32":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
                user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)  # RESTORE / SHOW
                user32.SetForegroundWindow(hwnd)
            except (AttributeError, OSError):
                pass
        root.focus_force()

    def check():
        try:
            if root.state() == "iconic":
                restore()
            root.after(interval_ms, check)
        except tk.TclError:  # window already closed
            pass

    root.after(100, restore)
    root.after(interval_ms, check)
    return check
