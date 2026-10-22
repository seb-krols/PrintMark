from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from .footprint import polygons
from .placement import auto_place
from .ui_common import ACCENT, BG, DANGER, FONT, INK, LINE, MUTED, brand, center, divider, style


class PlacementWindow:
    def __init__(
        self, root, footprint, surface, placed, settings, material, part_id, *, demo=False
    ):
        self.root, self.footprint, self.surface = root, footprint, surface
        self.placed, self.initial, self.settings = placed, placed, settings
        self.result = None
        self.drag_anchor = None
        self.demo = demo
        root.title("BaseMark · Place your stamp" + (" · Demo" if demo else ""))
        root.minsize(820, 590)
        style(root)
        brand(
            root,
            "PLACEMENT / DEMO" if demo else "PLACEMENT / EXPORT",
            "Give this part an identity.",
            "A small mark on the bottom. A material you can identify long after printing.",
        )
        divider(root)
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=28, pady=20)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        drawing = ttk.Frame(body)
        drawing.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        self.canvas = tk.Canvas(
            drawing,
            background="#ecefe9",
            highlightthickness=1,
            highlightbackground=LINE,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        ttk.Label(
            drawing,
            text="UNDERSIDE VIEW    •    Dimensions in mm    •    Drag the stamp to move",
            font=(FONT, 9),
            foreground=MUTED,
        ).pack(anchor="w", pady=(10, 0))
        sidebar = ttk.Frame(body, width=240)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)
        ttk.Label(sidebar, text="YOUR STAMP", foreground=MUTED, font=(FONT, 9, "bold")).pack(
            anchor="w"
        )
        ttk.Label(sidebar, text=placed.text, font=(FONT, 18, "bold"), wraplength=235).pack(
            anchor="w", pady=(10, 14)
        )
        for label, value in [
            ("Material", material),
            ("Part ID", part_id),
            ("Depth", f"{settings.layers} layers"),
            ("Edge margin", f"{settings.margin_mm:g} mm"),
        ]:
            row = ttk.Frame(sidebar)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, foreground=MUTED).pack(side="left")
            ttk.Label(row, text=value, font=(FONT, 10, "bold")).pack(side="right")
        ttk.Separator(sidebar).pack(fill="x", pady=12)
        ttk.Label(sidebar, text="Text height", style="Heading.TLabel").pack(anchor="w")
        sizing = ttk.Frame(sidebar)
        sizing.pack(fill="x", pady=(8, 10))
        ttk.Button(sizing, text="−", width=3, command=lambda: self.resize(-0.5)).pack(side="left")
        self.height_label = ttk.Label(sizing, text="", anchor="center", width=10)
        self.height_label.pack(side="left", expand=True)
        ttk.Button(sizing, text="+", width=3, command=lambda: self.resize(0.5)).pack(side="right")
        ttk.Button(sidebar, text="↻  Rotate 90°", command=self.rotate).pack(fill="x", pady=(0, 8))
        ttk.Button(sidebar, text="Auto place", command=self.auto).pack(fill="x")
        self.status = ttk.Label(sidebar, text="", wraplength=235, font=(FONT, 10, "bold"))
        self.status.pack(anchor="w", pady=(14, 7))
        ttk.Label(
            sidebar,
            text="Text is shown as you’ll read it from underneath. The toolpath is "
            "mirrored automatically.",
            wraplength=235,
            foreground=MUTED,
        ).pack(anchor="w")
        separator = tk.Frame(root, background=LINE, height=1)
        separator.pack(side="bottom", fill="x", before=body)
        footer = ttk.Frame(root)
        footer.pack(side="bottom", fill="x", padx=28, pady=18, before=separator)
        ttk.Label(
            footer,
            text="Demo only · no file or counter changes"
            if demo
            else "Sealing face or delicate part? Skip this label.",
            foreground=MUTED,
        ).pack(side="left")
        self.ok = ttk.Button(
            footer,
            text="Close preview" if demo else "Apply stamp  →",
            style="Accent.TButton",
            command=self.accept,
        )
        self.ok.pack(side="right", padx=(10, 0))
        ttk.Button(footer, text="Skip label", command=self.skip).pack(side="right")
        self.canvas.bind("<Configure>", self.draw)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag_anchor", None))
        root.bind("<Return>", lambda _: self.accept())
        root.bind("<Escape>", lambda _: self.skip())
        root.bind("<Key-plus>", lambda _: self.resize(0.5))
        root.bind("<Key-equal>", lambda _: self.resize(0.5))
        root.bind("<Key-minus>", lambda _: self.resize(-0.5))
        root.bind("<Key-r>", lambda _: self.rotate())
        root.protocol("WM_DELETE_WINDOW", self.skip)
        center(root, 1080, 740)
        root.attributes("-topmost", True)

    def transform(self):
        left, bottom, right, top = self.footprint.bounds
        w, h = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        scale = min((w - 80) / (right - left), (h - 80) / (top - bottom))
        return scale, (left + right) / 2, (bottom + top) / 2, w / 2, h / 2

    def screen(self, x, y):
        scale, cx, cy, sx, sy = self.transform()
        return sx - (x - cx) * scale, sy - (y - cy) * scale

    def world(self, x, y):
        scale, cx, cy, sx, sy = self.transform()
        return cx - (x - sx) / scale, cy - (y - sy) / scale

    def geometry(self, geometry, fill, holes, outline=""):
        for poly in polygons(geometry):
            coords = [v for x, y in poly.exterior.coords for v in self.screen(x, y)]
            self.canvas.create_polygon(coords, fill=fill, outline=outline, width=1)
            for ring in poly.interiors:
                coords = [v for x, y in ring.coords for v in self.screen(x, y)]
                self.canvas.create_polygon(coords, fill=holes, outline=outline, width=1)

    def draw(self, _event=None):
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        for x in range(16, w, 24):
            for y in range(16, h, 24):
                self.canvas.create_oval(x, y, x + 1, y + 1, fill="#cdd6cc", outline="")
        self.geometry(self.footprint, "#d3dcd2", "#ecefe9", "#9caca0")
        self.geometry(self.surface, "#e4eae0", "#d3dcd2")
        # The eroded region's holes are wider than the real part's holes. Restore
        # actual voids after drawing the margin band so they cannot look solid.
        for poly in polygons(self.footprint):
            for ring in poly.interiors:
                coords = [v for x, y in ring.coords for v in self.screen(x, y)]
                self.canvas.create_polygon(coords, fill="#ecefe9", outline="#9caca0")
        valid = self.placed.fits(self.surface)
        color = ACCENT if valid else DANGER
        self.geometry(self.placed.geometry, color, "#e4eae0")
        left, bottom, right, top = self.placed.geometry.bounds
        a, b = self.screen(left, bottom), self.screen(right, top)
        self.canvas.create_rectangle(*a, *b, outline=color, dash=(4, 3), width=1)
        for x, y in [a, b, (a[0], b[1]), (b[0], a[1])]:
            self.canvas.create_rectangle(x - 3, y - 3, x + 3, y + 3, fill=BG, outline=color)
        scale, *_ = self.transform()
        self.canvas.create_line(26, h - 28, 26 + 10 * scale, h - 28, fill=INK, width=2)
        self.canvas.create_text(26, h - 40, text="10 mm", anchor="w", fill=MUTED, font=(FONT, 9))
        self.height_label.configure(text=f"{self.placed.height:g} mm")
        self.status.configure(
            text="✓  Fits the solid surface" if valid else "Move inside the safe area",
            foreground=color,
        )
        self.ok.configure(state="normal" if valid else "disabled")

    def start_drag(self, event):
        from shapely.geometry import Point

        x, y = self.world(event.x, event.y)
        if self.placed.geometry.envelope.buffer(2).covers(Point(x, y)):
            self.drag_anchor = (x - self.placed.x, y - self.placed.y)

    def drag(self, event):
        if self.drag_anchor:
            x, y = self.world(event.x, event.y)
            self.placed = replace(self.placed, x=x - self.drag_anchor[0], y=y - self.drag_anchor[1])
            self.draw()

    def resize(self, delta):
        height = min(12.0, max(self.settings.min_text_height_mm, self.placed.height + delta))
        self.placed = replace(self.placed, height=height)
        self.draw()

    def rotate(self):
        self.placed = replace(self.placed, angle=(self.placed.angle + 90) % 360)
        self.draw()

    def auto(self):
        try:
            self.placed = auto_place(
                self.initial.text,
                self.surface,
                self.placed.height,
                self.settings.min_text_height_mm,
            )
        except Exception:
            self.placed = self.initial
        self.draw()

    def accept(self):
        if self.placed.fits(self.surface):
            self.result = self.placed
            self.root.destroy()

    def skip(self):
        self.result = None
        self.root.destroy()


def choose_placement(footprint, surface, placed, settings, material, part_id, *, demo=False):
    try:
        root = tk.Tk()
    except tk.TclError:
        print("BaseMark: no display available; using automatic placement.", file=sys.stderr)
        return placed
    try:
        window = PlacementWindow(
            root, footprint, surface, placed, settings, material, part_id, demo=demo
        )
        root.mainloop()
        return window.result
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
