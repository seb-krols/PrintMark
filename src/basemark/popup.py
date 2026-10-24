from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from . import ui_common as ui
from .footprint import polygons
from .placement import auto_place


class PlacementWindow:
    """Shown during a PrusaSlicer export: confirm or adjust where the label goes."""

    def __init__(
        self,
        root,
        footprint,
        surface,
        placed,
        settings,
        material,
        part_id,
        job_name="",
        *,
        demo=False,
    ):
        self.root, self.footprint, self.surface = root, footprint, surface
        self.placed, self.initial, self.settings = placed, placed, settings
        self.result = None
        self.drag_anchor = None
        self.demo = demo
        root.title("BaseMark · Stamp this export" + (" (demo)" if demo else ""))
        ui.style(root)
        root.minsize(ui.px(760), ui.px(520))
        px = ui.px

        header = ttk.Frame(root, padding=(px(24), px(16), px(24), px(12)))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="DEMO · NOTHING IS SAVED" if demo else "PRUSASLICER EXPORT",
            style="Eyebrow.TLabel",
        ).pack(anchor="w")
        ttk.Label(header, text="Stamp this export", style="Title.TLabel").pack(anchor="w")
        details = [material, f"ID {part_id}"] + ([job_name] if job_name else [])
        ttk.Label(header, text="   ·   ".join(details), style="Muted.TLabel").pack(anchor="w")

        footer = ttk.Frame(root, padding=(px(24), px(12), px(24), px(16)))
        footer.pack(side="bottom", fill="x")
        tk.Frame(root, background=ui.LINE, height=1).pack(side="bottom", fill="x")
        ttk.Label(
            footer,
            text="Enter apply  ·  Esc skip  ·  R rotate  ·  + / − size",
            style="Small.TLabel",
        ).pack(side="left")
        self.ok = ttk.Button(
            footer,
            text="Close demo" if demo else "Apply stamp",
            style="Big.Accent.TButton",
            command=self.accept,
        )
        self.ok.pack(side="right")
        ttk.Button(footer, text="Skip label", style="Big.TButton", command=self.skip).pack(
            side="right", padx=(0, px(10))
        )

        body = ttk.Frame(root, padding=(px(24), 0, px(24), px(16)))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        view = tk.Frame(
            body, background=ui.CANVAS, highlightthickness=1, highlightbackground=ui.LINE
        )
        view.grid(row=0, column=0, sticky="nsew", padx=(0, px(16)))
        self.canvas = tk.Canvas(view, background=ui.CANVAS, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)

        side_frame, side = ui.card(body)
        side_frame.grid(row=0, column=1, sticky="ns")
        side_frame.configure(width=px(270))
        side_frame.pack_propagate(False)
        ttk.Label(side, text="LABEL", style="Card.Eyebrow.TLabel").pack(anchor="w")
        tk.Label(
            side,
            text=placed.text,
            font=(ui.SEMIBOLD, 17),
            foreground=ui.INK,
            background=ui.PANEL,
            wraplength=px(230),
            justify="left",
        ).pack(anchor="w", pady=(px(2), px(10)))
        self.status = tk.Label(
            side, text="", font=(ui.SEMIBOLD, 10), padx=px(10), pady=px(5), anchor="w"
        )
        self.status.pack(fill="x", pady=(0, px(16)))

        ttk.Label(side, text="TEXT HEIGHT", style="Card.Eyebrow.TLabel").pack(anchor="w")
        sizing = ttk.Frame(side, style="Card.TFrame")
        sizing.pack(fill="x", pady=(px(6), px(14)))
        ttk.Button(sizing, text="−", width=3, command=lambda: self.resize(-0.5)).pack(side="left")
        self.height_label = ttk.Label(
            sizing, text="", style="Value.TLabel", anchor="center", font=(ui.SEMIBOLD, 12)
        )
        self.height_label.pack(side="left", fill="x", expand=True)
        ttk.Button(sizing, text="+", width=3, command=lambda: self.resize(0.5)).pack(side="right")

        ttk.Button(side, text="↻  Rotate 90°", command=self.rotate).pack(fill="x")
        ttk.Button(side, text="Auto place", command=self.auto).pack(fill="x", pady=(px(8), 0))

        ttk.Separator(side).pack(fill="x", pady=px(16))
        for label, value in [
            ("Depth", f"{settings.layers} layer{'s' if settings.layers != 1 else ''}"),
            ("Edge margin", f"{settings.margin_mm:g} mm"),
        ]:
            row = ttk.Frame(side, style="Card.TFrame")
            row.pack(fill="x", pady=px(2))
            ttk.Label(row, text=label, style="Card.Muted.TLabel").pack(side="left")
            ttk.Label(row, text=value, style="Value.TLabel").pack(side="right")
        ttk.Label(
            side,
            text="Viewed from underneath, as you will read it on the part. The toolpath is "
            "mirrored automatically.",
            style="Card.Small.TLabel",
            wraplength=px(230),
        ).pack(anchor="w", pady=(px(12), 0))

        self.canvas.bind("<Configure>", self.draw)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag_anchor", None))
        root.bind("<Return>", lambda _: self.accept())
        root.bind("<KP_Enter>", lambda _: self.accept())
        root.bind("<Escape>", lambda _: self.skip())
        for key in ("<Key-plus>", "<Key-equal>", "<KP_Add>"):
            root.bind(key, lambda _: self.resize(0.5))
        for key in ("<Key-minus>", "<KP_Subtract>"):
            root.bind(key, lambda _: self.resize(-0.5))
        root.bind("<Key-r>", lambda _: self.rotate())
        root.bind("<Key-a>", lambda _: self.auto())
        root.protocol("WM_DELETE_WINDOW", self.skip)
        ui.center(root, 1040, 700)
        self.keep_visible = ui.keep_visible(root)

    def transform(self):
        left, bottom, right, top = self.footprint.bounds
        w, h = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        margin = ui.px(56)
        scale = min((w - 2 * margin) / (right - left), (h - 2 * margin) / (top - bottom))
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
        px, c = ui.px, self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        step = px(24)
        for x in range(step // 2, w, step):
            for y in range(step // 2, h, step):
                c.create_rectangle(x, y, x + 1, y + 1, fill="#d4dad3", outline="")
        # Part outline, then the safe area inside the edge margin.
        self.geometry(self.footprint, "#d7ded5", ui.CANVAS, "#a9b5ab")
        self.geometry(self.surface, "#f9faf8", "#d7ded5")
        # The eroded region's holes are wider than the real part's holes. Restore actual
        # voids after drawing the margin band so they cannot look solid.
        for poly in polygons(self.footprint):
            for ring in poly.interiors:
                coords = [v for x, y in ring.coords for v in self.screen(x, y)]
                c.create_polygon(coords, fill=ui.CANVAS, outline="#a9b5ab")
        valid = self.placed.fits(self.surface)
        colour = ui.ACCENT if valid else ui.DANGER
        self.geometry(self.placed.geometry, colour, "#f9faf8")
        left, bottom, right, top = self.placed.geometry.bounds
        a, b = self.screen(left, bottom), self.screen(right, top)
        pad = px(5)
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        c.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad, outline=colour, dash=(4, 3))
        knob = px(3)
        for x, y in [
            (x0 - pad, y0 - pad),
            (x1 + pad, y0 - pad),
            (x0 - pad, y1 + pad),
            (x1 + pad, y1 + pad),
        ]:
            c.create_rectangle(x - knob, y - knob, x + knob, y + knob, fill="white", outline=colour)
        scale, *_ = self.transform()
        bar = 10 * scale
        c.create_line(px(20), h - px(22), px(20) + bar, h - px(22), fill=ui.INK, width=px(2))
        c.create_text(
            px(20), h - px(32), text="10 mm", anchor="sw", fill=ui.MUTED, font=(ui.FONT, 9)
        )
        c.create_text(
            px(16),
            px(14),
            text="UNDERSIDE VIEW  ·  drag the label to move it",
            anchor="nw",
            fill=ui.SUBTLE,
            font=(ui.SEMIBOLD, 8),
        )
        self.height_label.configure(text=f"{self.placed.height:g} mm")
        self.status.configure(
            text="✓  Fits the solid area" if valid else "✕  Outside the solid area",
            foreground=colour,
            background=ui.ACCENT_SOFT if valid else ui.DANGER_SOFT,
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


def choose_placement(
    footprint, surface, placed, settings, material, part_id, job_name="", *, demo=False
):
    ui.enable_dpi_awareness()
    try:
        root = tk.Tk()
    except tk.TclError:
        print("BaseMark: no display available; using automatic placement.", file=sys.stderr)
        return placed
    try:
        window = PlacementWindow(
            root, footprint, surface, placed, settings, material, part_id, job_name, demo=demo
        )
        root.mainloop()
        return window.result
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
