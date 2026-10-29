from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from shapely.geometry import Point
from shapely.ops import polylabel

from . import ui_common as ui
from .errors import SafeSkip
from .footprint import polygons
from .placement import Placement, auto_place

try:  # Tk's canvas cannot anti-alias; Pillow renders smooth outlines and lettering.
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # source installs without Pillow fall back to plain canvas shapes
    Image = None

SUPERSAMPLE = 3  # draw at 3x and shrink: smooth edges at any display scaling
GRID, PART, PART_EDGE, SAFE = "#d4dad3", "#d7ded5", "#a9b5ab", "#f9faf8"
OTHER_LABEL = "#6fa597"  # labels of the parts that are not selected
HAND_MINIMUM = 2.0  # by hand the text may go below the automatic minimum, e.g. a tiny part


class PlacementWindow:
    """Shown during a PrusaSlicer export: confirm or adjust where the labels go.

    A plate of several parts gets one label per part. Click a part (or its label) to
    select it; the controls on the right act on the selected part only.
    """

    def __init__(self, root, plate, placements, settings, material, part_id, *, demo=False):
        self.root, self.plate, self.settings = root, plate, settings
        self.footprint, self.parts = plate.footprint, plate.parts
        self.placements = list(placements)
        self.initial = list(placements)
        self.remembered = list(placements)  # restored when a part is switched back on
        self.text = next(p.text for p in placements if p is not None)
        self.multi = len(self.parts) > 1
        self.index = next(i for i, p in enumerate(placements) if p is not None)
        self.zoomed = False
        self.result = None
        self.drag_anchor = None
        self.demo = demo
        self.label_cache = {}
        root.title("BaseMark · Stamp this export" + (" (demo)" if demo else ""))
        ui.style(root)
        root.minsize(ui.px(760), ui.px(540))
        px = ui.px

        header = ttk.Frame(root, padding=(px(24), px(16), px(24), px(12)))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="DEMO · NOTHING IS SAVED" if demo else "PRUSASLICER EXPORT",
            style="Eyebrow.TLabel",
        ).pack(anchor="w")
        ttk.Label(header, text="Stamp this export", style="Title.TLabel").pack(anchor="w")
        details = (
            [material]
            + ([f"ID {part_id}"] if part_id else [])
            + ([f"{len(self.parts)} parts"] if self.multi else [])
            + ([plate.job_name] if plate.job_name else [])
        )
        ttk.Label(header, text="   ·   ".join(details), style="Muted.TLabel").pack(anchor="w")

        footer = ttk.Frame(root, padding=(px(24), px(12), px(24), px(16)))
        footer.pack(side="bottom", fill="x")
        tk.Frame(root, background=ui.LINE, height=1).pack(side="bottom", fill="x")
        hints = "Enter apply  ·  Esc skip  ·  R rotate  ·  + / − size"
        if self.multi:
            hints += "  ·  Tab next part  ·  Z zoom"
        ttk.Label(footer, text=hints, style="Small.TLabel").pack(side="left")
        self.ok = ttk.Button(footer, text="", style="Big.Accent.TButton", command=self.accept)
        self.ok.pack(side="right")
        ttk.Button(
            footer,
            text="Skip all" if self.multi else "Skip label",
            style="Big.TButton",
            command=self.skip,
        ).pack(side="right", padx=(0, px(10)))

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
        self.included = tk.BooleanVar(value=True)
        if self.multi:
            nav = ttk.Frame(side, style="Card.TFrame")
            nav.pack(fill="x")
            self.part_count = ttk.Label(nav, text="", style="Card.Eyebrow.TLabel")
            self.part_count.pack(side="left")
            ttk.Button(nav, text="›", width=2, command=lambda: self.step(1)).pack(side="right")
            ttk.Button(nav, text="‹", width=2, command=lambda: self.step(-1)).pack(
                side="right", padx=(0, px(4))
            )
            self.part_name = tk.Label(
                side,
                text="",
                font=(ui.SEMIBOLD, 11),
                foreground=ui.INK,
                background=ui.PANEL,
                wraplength=px(230),
                justify="left",
                anchor="w",
            )
            self.part_name.pack(fill="x", pady=(px(4), px(6)))
            include_row = ttk.Frame(side, style="Card.TFrame")
            include_row.pack(fill="x", pady=(0, px(4)))
            ui.Switch(include_row, self.included, command=self.toggle_part).pack(side="left")
            ttk.Label(include_row, text="Stamp this part", style="Card.TLabel").pack(
                side="left", padx=px(10)
            )
            ttk.Separator(side).pack(fill="x", pady=px(10))
        ttk.Label(side, text="LABEL", style="Card.Eyebrow.TLabel").pack(anchor="w")
        tk.Label(
            side,
            text=self.text,
            font=(ui.SEMIBOLD, 17),
            foreground=ui.INK,
            background=ui.PANEL,
            wraplength=px(230),
            justify="left",
        ).pack(anchor="w", pady=(px(2), px(8)))
        self.status = tk.Label(
            side, text="", font=(ui.SEMIBOLD, 10), padx=px(10), pady=px(5), anchor="w"
        )
        self.status.pack(fill="x", pady=(0, px(12)))

        ttk.Label(side, text="TEXT HEIGHT", style="Card.Eyebrow.TLabel").pack(anchor="w")
        sizing = ttk.Frame(side, style="Card.TFrame")
        sizing.pack(fill="x", pady=(px(6), px(12)))
        self.smaller = ttk.Button(sizing, text="−", width=3, command=lambda: self.resize(-0.5))
        self.smaller.pack(side="left")
        self.height_label = ttk.Label(
            sizing, text="", style="Value.TLabel", anchor="center", font=(ui.SEMIBOLD, 12)
        )
        self.height_label.pack(side="left", fill="x", expand=True)
        self.larger = ttk.Button(sizing, text="+", width=3, command=lambda: self.resize(0.5))
        self.larger.pack(side="right")

        self.rotate_button = ttk.Button(side, text="↻  Rotate 90°", command=self.rotate)
        self.rotate_button.pack(fill="x")
        self.auto_button = ttk.Button(side, text="Auto place", command=self.auto)
        self.auto_button.pack(fill="x", pady=(px(8), 0))
        if self.multi:
            self.zoom_button = ttk.Button(side, text="", command=self.toggle_zoom)
            self.zoom_button.pack(fill="x", pady=(px(8), 0))

        ttk.Separator(side).pack(fill="x", pady=px(14))
        for label, value in [
            ("Depth", f"{settings.layers} layer{'s' if settings.layers != 1 else ''}"),
            ("Edge margin", f"{settings.margin_mm:g} mm"),
        ]:
            row = ttk.Frame(side, style="Card.TFrame")
            row.pack(fill="x", pady=px(2))
            ttk.Label(row, text=label, style="Card.Muted.TLabel").pack(side="left")
            ttk.Label(row, text=value, style="Value.TLabel").pack(side="right")
        if not self.multi:  # the plate controls need the room; the canvas says "underside"
            ttk.Label(
                side,
                text="Viewed from underneath, as you will read it on the part. The toolpath "
                "is mirrored automatically.",
                style="Card.Small.TLabel",
                wraplength=px(230),
            ).pack(anchor="w", pady=(px(10), 0))

        self.scene = self.scene_key = self.redraw = None
        self.canvas.bind("<Configure>", self.resized)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag_anchor", None))
        self.canvas.bind("<Double-Button-1>", lambda _: self.multi and self.toggle_zoom())
        root.bind("<Return>", lambda _: self.accept())
        root.bind("<KP_Enter>", lambda _: self.accept())
        root.bind("<Escape>", lambda _: self.skip())
        for key in ("<Key-plus>", "<Key-equal>", "<KP_Add>"):
            root.bind(key, lambda _: self.resize(0.5))
        for key in ("<Key-minus>", "<KP_Subtract>"):
            root.bind(key, lambda _: self.resize(-0.5))
        root.bind("<Key-r>", lambda _: self.rotate())
        root.bind("<Key-a>", lambda _: self.auto())
        if self.multi:
            root.bind("<Tab>", lambda _: self.step(1) or "break")
            root.bind("<Shift-Tab>", lambda _: self.step(-1) or "break")
            root.bind("<Key-z>", lambda _: self.toggle_zoom())
        root.protocol("WM_DELETE_WINDOW", self.skip)
        ui.center(root, 1040, 720)
        self.refresh_side()
        self.keep_visible = ui.keep_visible(root)

    # ---------- the selected part ----------

    @property
    def part(self):
        return self.parts[self.index]

    @property
    def placed(self) -> Placement | None:
        return self.placements[self.index]

    @placed.setter
    def placed(self, value):
        self.placements[self.index] = value

    def fits(self, index) -> bool:
        placed = self.placements[index]
        return placed is not None and placed.fits(self.parts[index].surface)

    def select(self, index):
        if index != self.index:
            self.index = index
            self.refresh_side()
            self.draw()

    def step(self, delta):
        self.select((self.index + delta) % len(self.parts))

    def toggle_part(self):
        if self.included.get():
            self.placed = self.remembered[self.index] or self.fallback()
        else:
            self.remembered[self.index] = self.placed
            self.placed = None
        self.draw()

    def fallback(self) -> Placement:
        """A label for a part where automatic placement found no room."""
        try:
            return auto_place(
                self.text, self.part.surface, self.settings.text_height_mm, HAND_MINIMUM
            )
        except SafeSkip:
            area = self.part.surface if self.part.usable else self.part.outline
            region = max(polygons(area), key=lambda p: p.area)
            centre = polylabel(region, tolerance=0.3)
            return Placement(self.text, HAND_MINIMUM, centre.x, centre.y)

    def toggle_zoom(self):
        self.zoomed = not self.zoomed
        self.draw()

    def refresh_side(self):
        """Controls and texts for the selected part, plus the Apply button."""
        placed = self.placed
        if self.multi:
            self.part_count.configure(text=f"PART {self.index + 1} OF {len(self.parts)}")
            self.part_name.configure(text=self.part.name)
            self.included.set(placed is not None)
            self.zoom_button.configure(
                text="Show the whole plate" if self.zoomed else "Zoom to this part"
            )
        for button in (self.smaller, self.larger, self.rotate_button, self.auto_button):
            button.configure(state="normal" if placed is not None else "disabled")
        self.height_label.configure(text=f"{placed.height:g} mm" if placed else "—")
        if placed is None:
            text = "Too small for a label" if self.initial[self.index] is None else "No label"
            self.status.configure(text=f"–  {text}", foreground=ui.MUTED, background=ui.BUTTON)
        elif self.fits(self.index):
            self.status.configure(
                text="✓  Fits the solid area", foreground=ui.ACCENT, background=ui.ACCENT_SOFT
            )
        else:
            self.status.configure(
                text="✕  Outside the solid area", foreground=ui.DANGER, background=ui.DANGER_SOFT
            )
        stamped = [i for i, p in enumerate(self.placements) if p is not None]
        ready = bool(stamped) and all(self.fits(i) for i in stamped)
        if self.demo:
            text = "Close demo"
        elif not self.multi:
            text = "Apply stamp"
        else:
            text = f"Stamp {len(stamped)} part{'s' if len(stamped) != 1 else ''}"
        self.ok.configure(text=text, state="normal" if ready else "disabled")

    # ---------- drawing ----------

    def view_bounds(self):
        if self.zoomed:
            left, bottom, right, top = self.part.outline.bounds
            pad = max(3.0, 0.15 * max(right - left, top - bottom))
            return left - pad, bottom - pad, right + pad, top + pad
        return self.footprint.bounds

    def transform(self):
        left, bottom, right, top = self.view_bounds()
        w, h = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        margin = ui.px(56)
        scale = min(
            (w - 2 * margin) / max(right - left, 1e-6), (h - 2 * margin) / max(top - bottom, 1e-6)
        )
        return scale, (left + right) / 2, (bottom + top) / 2, w / 2, h / 2

    def screen(self, x, y):
        scale, cx, cy, sx, sy = self.transform()
        return sx - (x - cx) * scale, sy - (y - cy) * scale

    def world(self, x, y):
        scale, cx, cy, sx, sy = self.transform()
        return cx - (x - sx) / scale, cy - (y - sy) / scale

    def resized(self, _event=None):
        # Window resizing sends a burst of events; repaint once it settles.
        if self.redraw:
            self.root.after_cancel(self.redraw)
        if self.scene_key is None:  # first paint: no blank window
            self.redraw = self.root.after_idle(self.draw)
        else:
            self.redraw = self.root.after(40, self.draw)

    def rings(self, geometry):
        """Screen-space (exterior, [holes]) for each polygon of a shapely geometry."""
        for poly in polygons(geometry):
            yield (
                [self.screen(x, y) for x, y in poly.exterior.coords],
                [[self.screen(x, y) for x, y in ring.coords] for ring in poly.interiors],
            )

    def paint_scene(self, w, h):
        """Grid, part outlines and solid areas as one smooth image."""
        k = SUPERSAMPLE
        image = Image.new("RGB", (w * k, h * k), ui.CANVAS)
        pen = ImageDraw.Draw(image)
        step, dot = ui.px(24) * k, max(1, ui.px(1)) * k
        for x in range(step // 2, w * k, step):
            for y in range(step // 2, h * k, step):
                pen.rectangle((x, y, x + dot, y + dot), fill=GRID)

        def scaled(ring):
            return [(x * k, y * k) for x, y in ring]

        edge = max(1, ui.px(1)) * k
        for outer, _ in self.rings(self.footprint):
            pen.polygon(scaled(outer), fill=PART, outline=PART_EDGE, width=edge)
        # Parts without a label show no solid area, so they read as "not stamped".
        for index, part in enumerate(self.parts):
            if self.placements[index] is None:
                continue
            for outer, holes in self.rings(part.surface):
                pen.polygon(scaled(outer), fill=SAFE)
                for hole in holes:
                    pen.polygon(scaled(hole), fill=PART)
        # The eroded region's holes are wider than the real part's holes. Restore actual
        # voids after drawing the margin band so they cannot look solid.
        for _, holes in self.rings(self.footprint):
            for hole in holes:
                pen.polygon(scaled(hole), fill=ui.CANVAS, outline=PART_EDGE, width=edge)
        if self.multi:
            for outer, _ in self.rings(self.part.outline):
                pen.line(scaled(outer), fill=ui.ACCENT, width=2 * edge, joint="curve")
        return ImageTk.PhotoImage(image.reduce(k), master=self.canvas)

    def paint_label(self, placed, colour):
        """The lettering as a small transparent image; returns it and its screen origin."""
        shapes = list(self.rings(placed.geometry))
        points = [point for outer, _ in shapes for point in outer]
        left = int(min(x for x, _ in points)) - 1
        top = int(min(y for _, y in points)) - 1
        width = int(max(x for x, _ in points)) - left + 2
        height = int(max(y for _, y in points)) - top + 2
        k = SUPERSAMPLE
        image = Image.new("RGBA", (width * k, height * k), (0, 0, 0, 0))
        pen = ImageDraw.Draw(image)

        def local(ring):
            return [((x - left) * k, (y - top) * k) for x, y in ring]

        for outer, holes in shapes:
            pen.polygon(local(outer), fill=colour)
            for hole in holes:  # counters of A, P, 0 … stay see-through
                pen.polygon(local(hole), fill=(0, 0, 0, 0))
        return ImageTk.PhotoImage(image.reduce(k), master=self.canvas), left, top

    def vector(self, geometry, fill, holes, outline="", tags=()):
        """Fallback without Pillow: plain (aliased) canvas polygons."""
        for outer, rings in self.rings(geometry):
            coords = [v for point in outer for v in point]
            self.canvas.create_polygon(coords, fill=fill, outline=outline, tags=tags)
            for ring in rings:
                coords = [v for point in ring for v in point]
                self.canvas.create_polygon(coords, fill=holes, outline=outline, tags=tags)

    def draw(self, _event=None):
        """Repaint everything: the scene (cached while nothing changes) and the labels."""
        px, c = ui.px, self.canvas
        self.redraw = None
        c.delete("all")
        w, h = max(c.winfo_width(), 2), max(c.winfo_height(), 2)
        if Image is not None:
            key = (w, h, self.index, self.zoomed, tuple(p is None for p in self.placements))
            if self.scene_key != key:
                self.scene, self.scene_key = self.paint_scene(w, h), key
            c.create_image(0, 0, image=self.scene, anchor="nw")
        else:
            self.scene_key = (w, h)
            self.vector(self.footprint, PART, ui.CANVAS, PART_EDGE)
            for index, part in enumerate(self.parts):
                if self.placements[index] is not None:
                    self.vector(part.surface, SAFE, PART)
            for _, holes in self.rings(self.footprint):
                for hole in holes:
                    coords = [v for point in hole for v in point]
                    c.create_polygon(coords, fill=ui.CANVAS, outline=PART_EDGE)
            if self.multi:
                self.vector(self.part.outline, "", "", ui.ACCENT)
        scale, *_ = self.transform()
        bar = 10 * scale
        c.create_line(px(20), h - px(22), px(20) + bar, h - px(22), fill=ui.INK, width=px(2))
        c.create_text(
            px(20), h - px(32), text="10 mm", anchor="sw", fill=ui.MUTED, font=(ui.FONT, 9)
        )
        hint = "drag a label to move it"
        if self.multi:
            hint = "click a part to select it  ·  " + hint
        c.create_text(
            px(16),
            px(14),
            text=f"UNDERSIDE VIEW  ·  {hint}",
            anchor="nw",
            fill=ui.SUBTLE,
            font=(ui.SEMIBOLD, 8),
        )
        if self.multi:
            self.draw_numbers()
        for index in range(len(self.parts)):
            if index != self.index:
                self.draw_label(index)
        self.draw_label(self.index)
        self.refresh_side()

    def draw_numbers(self):
        """A small number at each part, matching "Part 2 of 4" on the right."""
        for index, part in enumerate(self.parts):
            points = [p for outer, _ in self.rings(part.outline) for p in outer]
            x = min(x for x, _ in points)
            y = min(y for _, y in points)
            chosen = index == self.index
            self.canvas.create_text(
                x,
                y - ui.px(4),
                text=str(index + 1),
                anchor="sw",
                fill=ui.ACCENT if chosen else ui.SUBTLE,
                font=(ui.SEMIBOLD, 9),
            )

    def label_image(self, index, colour):
        placed = self.placements[index]
        key = (index, placed, colour, self.transform())
        if key not in self.label_cache:
            if len(self.label_cache) > 64:
                self.label_cache.clear()
            self.label_cache[key] = self.paint_label(placed, colour)
        return self.label_cache[key]

    def draw_label(self, index):
        """Only the moved label is repainted while dragging; the scene image stays."""
        px, c = ui.px, self.canvas
        tag = f"label{index}"
        c.delete(tag)
        placed = self.placements[index]
        if placed is None:
            return
        chosen = index == self.index
        valid = self.fits(index)
        colour = (ui.ACCENT if chosen else OTHER_LABEL) if valid else ui.DANGER
        if Image is not None:
            image, left, top = self.label_image(index, colour)
            c.create_image(left, top, image=image, anchor="nw", tags=tag)
        else:
            self.vector(placed.geometry, colour, SAFE, tags=tag)
        if chosen:
            left, bottom, right, top = placed.geometry.bounds
            a, b = self.screen(left, bottom), self.screen(right, top)
            pad = px(5)
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            c.create_rectangle(
                x0 - pad, y0 - pad, x1 + pad, y1 + pad, outline=colour, dash=(4, 3), tags=tag
            )
            knob = px(3)
            for x, y in [
                (x0 - pad, y0 - pad),
                (x1 + pad, y0 - pad),
                (x0 - pad, y1 + pad),
                (x1 + pad, y1 + pad),
            ]:
                c.create_rectangle(
                    x - knob, y - knob, x + knob, y + knob, fill="white", outline=colour, tags=tag
                )

    # ---------- interaction ----------

    def start_drag(self, event):
        x, y = self.world(event.x, event.y)
        point = Point(x, y)
        reach = max(2.0, ui.px(6) / self.transform()[0])  # at least 6 screen pixels
        order = [self.index] + [i for i in range(len(self.parts)) if i != self.index]
        for index in order:
            placed = self.placements[index]
            if placed is not None and placed.geometry.envelope.buffer(reach).covers(point):
                self.select(index)
                self.drag_anchor = (x - placed.x, y - placed.y)
                return
        for index, part in enumerate(self.parts):
            if part.outline.buffer(reach).covers(point):
                self.select(index)
                return

    def drag(self, event):
        if self.drag_anchor and self.placed is not None:
            x, y = self.world(event.x, event.y)
            self.placed = replace(self.placed, x=x - self.drag_anchor[0], y=y - self.drag_anchor[1])
            self.draw_label(self.index)
            self.refresh_side()

    def resize(self, delta):
        # The operator sees the result before applying it, so allow the 2 mm hard limit.
        if self.placed is None:
            return
        height = min(12.0, max(HAND_MINIMUM, self.placed.height + delta))
        self.placed = replace(self.placed, height=height)
        self.draw()

    def rotate(self):
        if self.placed is None:
            return
        self.placed = replace(self.placed, angle=(self.placed.angle + 90) % 360)
        self.draw()

    def auto(self):
        if self.placed is None:
            return
        try:
            self.placed = auto_place(
                self.text,
                self.part.surface,
                self.placed.height,
                min(self.placed.height, self.settings.min_text_height_mm),
            )
        except SafeSkip:
            self.placed = self.initial[self.index] or self.placed
        self.draw()

    def accept(self):
        stamped = [i for i, p in enumerate(self.placements) if p is not None]
        if stamped and all(self.fits(i) for i in stamped):
            self.result = list(self.placements)
            self.root.destroy()

    def skip(self):
        self.result = None
        self.root.destroy()


def choose_placement(plate, placements, settings, material, part_id, *, demo=False):
    """The operator's labels (None for a part left out), or None to skip the export."""
    ui.enable_dpi_awareness()
    try:
        root = tk.Tk()
    except tk.TclError:
        print("BaseMark: no display available; using automatic placement.", file=sys.stderr)
        return placements
    try:
        window = PlacementWindow(root, plate, placements, settings, material, part_id, demo=demo)
        root.mainloop()
        return window.result
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
