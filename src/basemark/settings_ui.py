"""BaseMark settings app: status at a glance, one-click PrusaSlicer setup, part lookup."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from . import ui_common as ui
from .audit import format_records, lookup_id, read_log
from .config import Settings, load_settings, save_settings, validate_paths
from .counter import Counter
from .prusaslicer import SetupError, check, hook_command, setup

INTEGER_FIELDS = {"layers", "counter_digits", "counter_next"}
FLOAT_FIELDS = {"text_height_mm", "min_text_height_mm", "margin_mm"}
PAGES = [
    ("overview", "Overview"),
    ("stamp", "Stamp"),
    ("find", "Find part"),
    ("advanced", "Advanced"),
]


def local_time(stamp: str) -> str:
    try:
        moment = datetime.fromisoformat(stamp).astimezone()
    except (TypeError, ValueError):
        return stamp
    today = datetime.now().astimezone().date()
    day = "Today" if moment.date() == today else moment.strftime("%b %d").replace(" 0", " ")
    return f"{day}, {moment:%H:%M}"


def read_last_export(config: Path) -> dict | None:
    try:
        return json.loads((config.parent / "last-export.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class SettingsWindow:
    def __init__(self, root, path: Path):
        self.root, self.path = root, path
        self.settings = load_settings(path)
        self.values: dict[str, tk.Variable] = {}
        self.lookup_summary = ""
        ui.style(root)
        root.title("BaseMark")
        root.minsize(ui.px(780), ui.px(520))
        px = ui.px

        for key, value in asdict(self.settings).items():
            if key == "enabled":
                self.values[key] = tk.BooleanVar(value=value)
            elif key == "material_map":
                self.values[key] = tk.StringVar(value=json.dumps(value))
            elif key != "label":
                self.values[key] = tk.StringVar(value=str(value))
        counter_path, _ = self.settings.paths(path.parent)
        validate_paths(path, self.settings)
        with Counter(counter_path, self.settings.counter_next, recover=False) as counter:
            self.saved_next = counter.next
        self.values["counter_next"].set(str(self.saved_next))
        self.hook = tk.StringVar(value=hook_command(path))
        self.lookup_value = tk.StringVar()

        sidebar = ttk.Frame(root, style="Side.TFrame", padding=(px(14), px(20), px(14), px(16)))
        sidebar.pack(side="left", fill="y")
        tk.Frame(root, background=ui.LINE, width=1).pack(side="left", fill="y")
        brand = ttk.Frame(sidebar, style="Side.TFrame", padding=(px(8), 0, 0, px(22)))
        brand.pack(fill="x")
        mark = tk.Label(
            brand,
            text="B",
            font=(ui.SEMIBOLD, 12),
            foreground="white",
            background=ui.ACCENT,
            width=2,
        )
        mark.pack(side="left")
        names = ttk.Frame(brand, style="Side.TFrame", padding=(px(10), 0, 0, 0))
        names.pack(side="left")
        ttk.Label(names, text="BaseMark", style="Side.Heading.TLabel").pack(anchor="w")
        ttk.Label(names, text=f"Version {__version__}", style="Side.Small.TLabel").pack(anchor="w")
        self.nav: dict[str, tk.Label] = {}
        for key, title in PAGES:
            item = tk.Label(
                sidebar,
                text=title,
                anchor="w",
                font=(ui.FONT, 10),
                padx=px(12),
                pady=px(8),
                cursor="hand2",
                width=16,
            )
            item.pack(fill="x", pady=1)
            item.bind("<Button-1>", lambda _e, k=key: self.show(k))
            self.nav[key] = item
        ttk.Label(
            sidebar,
            text="Settings are saved automatically and apply to the next export.",
            style="Side.Small.TLabel",
            wraplength=px(150),
        ).pack(side="bottom", anchor="w", padx=px(8))

        main = ttk.Frame(root)
        main.pack(side="left", fill="both", expand=True)
        status_bar = ttk.Frame(main, padding=(px(28), px(8), px(28), px(10)))
        status_bar.pack(side="bottom", fill="x")
        self.feedback = ttk.Label(status_bar, text="", style="Small.TLabel")
        self.feedback.pack(side="left")
        tk.Frame(main, background=ui.LINE, height=1).pack(side="bottom", fill="x")
        self.pages: dict[str, ui.ScrollPage] = {}
        for key, _ in PAGES:
            self.pages[key] = ui.ScrollPage(main)
        self.build_overview(self.pages["overview"].body)
        self.build_stamp(self.pages["stamp"].body)
        self.build_find(self.pages["find"].body)
        self.build_advanced(self.pages["advanced"].body)
        root.bind("<Control-f>", lambda _e: self.show("find"))
        ui.center(root, 980, 680)
        self.show("overview")
        root.after(150, self.refresh_status)

    # ---------- layout helpers ----------

    def page_title(self, parent, title, subtitle):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text=subtitle, style="Muted.TLabel", wraplength=ui.px(640)).pack(
            anchor="w", pady=(ui.px(2), ui.px(18))
        )

    def entry(self, parent, key, width=8):
        field = ttk.Entry(parent, textvariable=self.values[key], width=width)
        field.bind("<FocusOut>", lambda _e: self.save())
        field.bind("<Return>", lambda _e: self.save())
        return field

    def setting_row(self, parent, title, help_text, control_factory, last=False):
        row = ttk.Frame(parent, style="Card.TFrame", padding=(0, ui.px(10)))
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        text = ttk.Frame(row, style="Card.TFrame")
        text.grid(row=0, column=0, sticky="w")
        ttk.Label(text, text=title, style="Value.TLabel").pack(anchor="w")
        ttk.Label(text, text=help_text, style="Card.Small.TLabel", wraplength=ui.px(400)).pack(
            anchor="w"
        )
        control = control_factory(row)
        control.grid(row=0, column=1, sticky="e", padx=(ui.px(16), 0))
        if not last:
            ttk.Separator(parent).pack(fill="x")
        return control

    def unit_entry(self, key, unit):
        def build(parent):
            frame = ttk.Frame(parent, style="Card.TFrame")
            self.entry(frame, key, width=6).pack(side="left")
            ttk.Label(frame, text=unit, style="Card.Muted.TLabel").pack(side="left", padx=(6, 0))
            return frame

        return build

    def show(self, key):
        for name, page in self.pages.items():
            page.pack_forget()
            chosen = name == key
            self.nav[name].configure(
                background=ui.PANEL if chosen else ui.SIDEBAR,
                foreground=ui.ACCENT if chosen else ui.INK,
                font=(ui.SEMIBOLD if chosen else ui.FONT, 10),
            )
        self.pages[key].pack(fill="both", expand=True)
        if key == "overview":
            self.refresh_overview()

    def say(self, text, tone="info"):
        colour = {"ok": ui.ACCENT, "bad": ui.DANGER, "warn": ui.WARN, "info": ui.MUTED}[tone]
        self.feedback.configure(text=text, foreground=colour)

    # ---------- overview ----------

    def build_overview(self, page):
        self.page_title(
            page,
            "Overview",
            "BaseMark stamps the material and a part ID into the bottom of every PrusaSlicer "
            "export, so even a failed print can be identified and recycled correctly.",
        )
        frame, self.status_card = ui.card(page, fill="x")
        top = ttk.Frame(self.status_card, style="Card.TFrame")
        top.pack(fill="x")
        self.status_icon = tk.Label(
            top, text="…", font=(ui.SEMIBOLD, 16), width=2, background=ui.PANEL
        )
        self.status_icon.pack(side="left", anchor="n", padx=(0, ui.px(12)))
        words = ttk.Frame(top, style="Card.TFrame")
        words.pack(side="left", fill="x", expand=True)
        self.status_title = ttk.Label(
            words, text="Checking PrusaSlicer…", style="Card.Heading.TLabel"
        )
        self.status_title.pack(anchor="w")
        self.status_text = ttk.Label(
            words, text="", style="Card.Muted.TLabel", wraplength=ui.px(460)
        )
        self.status_text.pack(anchor="w", pady=(ui.px(2), 0))
        actions = ttk.Frame(top, style="Card.TFrame")
        actions.pack(side="right", anchor="n")
        self.setup_button = ttk.Button(
            actions,
            text="Set up PrusaSlicer",
            style="Accent.TButton",
            command=self.setup_prusaslicer,
        )
        ttk.Button(actions, text="Check again", command=self.refresh_status).pack(side="right")
        self.findings = ttk.Frame(self.status_card, style="Card.TFrame")
        self.findings.pack(fill="x", pady=(ui.px(12), 0))

        row = ttk.Frame(page)
        row.pack(fill="x", pady=ui.px(14))
        row.columnconfigure((0, 1), weight=1, uniform="cards")
        left_frame, left = ui.card(row)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, ui.px(7)))
        ttk.Label(left, text="THIS COMPUTER", style="Card.Eyebrow.TLabel").pack(anchor="w")
        prefix_row = ttk.Frame(left, style="Card.TFrame")
        prefix_row.pack(fill="x", pady=(ui.px(8), ui.px(4)))
        ttk.Label(prefix_row, text="Prefix", style="Value.TLabel").pack(side="left")
        self.entry(prefix_row, "counter_prefix", width=6).pack(side="left", padx=ui.px(10))
        self.prefix_hint = ttk.Label(
            left, text="", style="Card.Small.TLabel", wraplength=ui.px(270)
        )
        self.prefix_hint.pack(anchor="w")
        ttk.Label(left, text="Next part ID", style="Card.Muted.TLabel").pack(
            anchor="w", pady=(ui.px(12), 0)
        )
        self.next_id = ttk.Label(left, text="", style="Big.TLabel")
        self.next_id.pack(anchor="w")

        right_frame, right = ui.card(row)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(ui.px(7), 0))
        ttk.Label(right, text="STAMPING", style="Card.Eyebrow.TLabel").pack(anchor="w")
        switch_row = ttk.Frame(right, style="Card.TFrame")
        switch_row.pack(fill="x", pady=(ui.px(8), ui.px(12)))
        ui.Switch(switch_row, self.values["enabled"], command=self.save).pack(side="left")
        self.enabled_text = ttk.Label(switch_row, text="", style="Value.TLabel")
        self.enabled_text.pack(side="left", padx=ui.px(10))
        ttk.Label(right, text="On each export", style="Card.Muted.TLabel").pack(anchor="w")
        ui.Segmented(
            right,
            self.values["mode"],
            [("interactive", "Let me place it"), ("auto", "Place automatically")],
            command=self.save,
        ).pack(anchor="w", pady=(ui.px(4), ui.px(12)))
        ttk.Label(right, text="Label preview", style="Card.Muted.TLabel").pack(anchor="w")
        self.preview = ttk.Label(right, text="", style="Value.TLabel", font=(ui.SEMIBOLD, 13))
        self.preview.pack(anchor="w")

        frame, recent = ui.card(page, fill="x")
        head = ttk.Frame(recent, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="RECENT EXPORTS", style="Card.Eyebrow.TLabel").pack(side="left")
        ttk.Button(head, text="Refresh", style="Link.TButton", command=self.refresh_overview).pack(
            side="right"
        )
        self.last_export = ttk.Frame(recent, style="Card.TFrame")
        self.last_export.pack(fill="x", pady=(ui.px(8), 0))
        self.history = ttk.Frame(recent, style="Card.TFrame")
        self.history.pack(fill="x")

    def refresh_overview(self):
        prefix = self.values["counter_prefix"].get().strip()
        digits = self.values["counter_digits"].get()
        try:
            next_id = prefix + str(int(self.values["counter_next"].get())).zfill(int(digits))
        except ValueError:
            next_id = "—"
        self.next_id.configure(text=next_id)
        self.prefix_hint.configure(
            text="Give every PC its own letter (A, B, …) so IDs never clash."
            if not prefix
            else "Unique to this PC. Labels and the log use it."
        )
        try:
            preview = (
                self.values["template"]
                .get()
                .format(
                    material="PLA",
                    id=next_id,
                    prefix=prefix,
                    date=datetime.now().date().isoformat(),
                )
            )
        except (KeyError, IndexError, ValueError):
            preview = "Template needs {material} and {id}"
        self.preview.configure(text=preview)
        self.enabled_text.configure(
            text="On — exports get a label"
            if self.values["enabled"].get()
            else "Off — exports unchanged"
        )
        for child in (*self.last_export.winfo_children(), *self.history.winfo_children()):
            child.destroy()
        report = read_last_export(self.path)
        if report:
            status = str(report.get("status", ""))
            tone = {"stamped": "ok", "skipped": "warn", "error": "bad"}.get(status, "info")
            line = ttk.Frame(self.last_export, style="Card.TFrame")
            line.pack(fill="x", pady=(0, ui.px(8)))
            ui.pill(line, status.upper() or "UNKNOWN", tone).pack(side="left", anchor="n")
            ttk.Label(
                line,
                text=f"{report.get('message', '')}\n{local_time(report.get('timestamp', ''))}"
                f" · {Path(str(report.get('source', ''))).name}",
                style="Card.Small.TLabel",
                wraplength=ui.px(560),
            ).pack(side="left", padx=ui.px(10))
        try:
            settings = load_settings(self.path)
            _, log = settings.paths(self.path.parent)
            rows = read_log(log)[-6:][::-1]
        except Exception as exc:
            ttk.Label(
                self.history, text=f"Could not read the log: {exc}", style="Card.Small.TLabel"
            ).pack(anchor="w")
            return
        if not rows:
            if not report:
                ttk.Label(
                    self.history,
                    text="Nothing yet. Slice a part in PrusaSlicer and click Export G-code.",
                    style="Card.Muted.TLabel",
                ).pack(anchor="w", pady=ui.px(6))
            return
        table = ttk.Frame(self.history, style="Card.TFrame")
        table.pack(fill="x")
        table.columnconfigure(2, weight=1)
        for column, title in enumerate(["ID", "MATERIAL", "FILE", "EXPORTED"]):
            ttk.Label(table, text=title, style="Card.Eyebrow.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0, ui.px(18)), pady=(0, ui.px(4))
            )
        for index, row in enumerate(rows, start=1):
            cells = [
                (row["id"], "Value.TLabel"),
                (row["material"], "Card.TLabel"),
                (Path(row["gcode_filename"]).name, "Card.Muted.TLabel"),
                (local_time(row["timestamp"]), "Card.Muted.TLabel"),
            ]
            for column, (text, style) in enumerate(cells):
                ttk.Label(table, text=text, style=style).grid(
                    row=index, column=column, sticky="w", padx=(0, ui.px(18)), pady=ui.px(2)
                )

    def refresh_status(self):
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            findings = check(load_settings(self.path), self.hook.get())
        except Exception as exc:
            findings = None
            self.render_status(False, "Could not check PrusaSlicer", str(exc), [])
        finally:
            self.root.configure(cursor="")
        if findings is None:
            return
        problems = [f for f in findings if f.ok is False]
        details = [f for f in findings if not f.text.startswith("PrusaSlicer settings:")]
        if not problems:
            self.render_status(
                True,
                "Ready to stamp",
                "PrusaSlicer runs BaseMark on every export with the presets below.",
                details,
            )
        else:
            self.render_status(
                False,
                "PrusaSlicer isn't ready yet",
                "Close PrusaSlicer, then click Set up PrusaSlicer. It adds “+ BaseMark” copies "
                "of your selected presets and leaves your own presets unchanged.",
                details,
            )

    def render_status(self, ready, title, text, findings):
        tone_fg, tone_bg = (ui.ACCENT, ui.ACCENT_SOFT) if ready else (ui.WARN, ui.WARN_SOFT)
        self.status_icon.configure(
            text="✓" if ready else "!", foreground=tone_fg, background=tone_bg
        )
        self.status_title.configure(text=title)
        self.status_text.configure(text=text)
        if ready:
            self.setup_button.pack_forget()
        elif not self.setup_button.winfo_ismapped():
            self.setup_button.pack(side="right", padx=(ui.px(8), 0))
        for child in self.findings.winfo_children():
            child.destroy()
        for finding in findings:
            line = ttk.Frame(self.findings, style="Card.TFrame")
            line.pack(fill="x", pady=1)
            ui.status_icon(line, finding.ok).pack(side="left", anchor="n")
            ttk.Label(
                line, text=finding.text, style="Card.Small.TLabel", wraplength=ui.px(600)
            ).pack(side="left", padx=(ui.px(6), 0))

    def setup_prusaslicer(self):
        try:
            done = setup(self.hook.get())
        except (SetupError, OSError) as exc:
            self.say(f"Not changed: {exc}", "bad")
            messagebox.showwarning("PrusaSlicer was not changed", str(exc), parent=self.root)
            return
        self.refresh_status()
        self.say(done[0] + " Open PrusaSlicer, slice and click Export G-code.", "ok")

    # ---------- stamp ----------

    def build_stamp(self, page):
        self.page_title(
            page,
            "Stamp",
            "How the label looks and how deep it goes. Filament Notes in PrusaSlicer can "
            "override these per material, e.g. basemark: layers=2; size=6.",
        )
        _, body = ui.card(page, fill="x")
        self.setting_row(
            body,
            "Text height",
            "Cap height of the letters, 4–12 mm. Larger text reads better.",
            self.unit_entry("text_height_mm", "mm"),
        )
        self.setting_row(
            body,
            "Smallest text",
            "Automatic placement may shrink the text down to this size to fit.",
            self.unit_entry("min_text_height_mm", "mm"),
        )
        self.setting_row(
            body,
            "Depth",
            "Bottom layers the text is cut into. Needs one more solid layer above it.",
            lambda parent: ui.Segmented(
                parent,
                self.values["layers"],
                [("1", "1 layer"), ("2", "2 layers"), ("3", "3 layers")],
                command=self.save,
            ),
        )
        self.setting_row(
            body,
            "Edge margin",
            "Minimum distance from the part's edges and holes.",
            self.unit_entry("margin_mm", "mm"),
        )
        self.setting_row(
            body,
            "Label text",
            "Use {material} and {id}; {date} and {prefix} are optional.",
            lambda parent: self.entry(parent, "template", width=22),
            last=True,
        )

    # ---------- find part ----------

    def build_find(self, page):
        self.page_title(
            page,
            "Find part",
            "Enter the ID printed under a part to see what it was. The search reads this PC's "
            "export log and does not use up an ID.",
        )
        search = ttk.Frame(page)
        search.pack(fill="x")
        field = ttk.Entry(search, textvariable=self.lookup_value, font=(ui.FONT, 12))
        field.pack(side="left", fill="x", expand=True)
        field.bind("<Return>", lambda _e: self.find_part())
        ttk.Button(search, text="Find", style="Accent.TButton", command=self.find_part).pack(
            side="left", padx=(ui.px(10), 0)
        )
        ttk.Label(
            page,
            text="Type it exactly, including the prefix and zeros, e.g. A001.",
            style="Small.TLabel",
        ).pack(anchor="w", pady=(ui.px(6), ui.px(14)))
        self.results = ttk.Frame(page)
        self.results.pack(fill="x")

    def find_part(self):
        for child in self.results.winfo_children():
            child.destroy()
        try:
            settings = load_settings(self.path)
            _, log = settings.paths(self.path.parent)
            rows = lookup_id(log, self.lookup_value.get())
        except Exception as exc:
            self.lookup_summary = f"Could not search the log: {exc}"
            ttk.Label(self.results, text=self.lookup_summary, style="Muted.TLabel").pack(anchor="w")
            return
        self.lookup_summary = format_records(rows)
        if not rows:
            _, body = ui.card(self.results, fill="x")
            ttk.Label(body, text="No part with this ID", style="Card.Heading.TLabel").pack(
                anchor="w"
            )
            ttk.Label(
                body,
                text="Check the prefix and leading zeros. Parts exported on another PC are in "
                "that PC's log.",
                style="Card.Muted.TLabel",
            ).pack(anchor="w")
            return
        if len(rows) > 1:
            ui.pill(
                self.results,
                "Several records share this ID — check before relying on it",
                "bad",
                ui.BG,
            ).pack(anchor="w", pady=(0, ui.px(8)))
        for row in rows:
            _, body = ui.card(self.results, fill="x", pady=(0, ui.px(10)))
            head = ttk.Frame(body, style="Card.TFrame")
            head.pack(fill="x", pady=(0, ui.px(10)))
            ttk.Label(head, text=row["id"], style="Big.TLabel").pack(side="left")
            ui.pill(head, row["material"], "ok").pack(side="left", padx=ui.px(12))
            grid = ttk.Frame(body, style="Card.TFrame")
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            facts = [
                ("Exported", local_time(row["timestamp"])),
                ("G-code file", row["gcode_filename"]),
                ("Objects", row["object_names"] or "—"),
                ("Computer", row["computer"]),
                ("Stamp", f"{row['layers']} layers · {row['text_height_mm']} mm text"),
            ]
            for index, (label, value) in enumerate(facts):
                ttk.Label(grid, text=label, style="Card.Muted.TLabel").grid(
                    row=index, column=0, sticky="nw", padx=(0, ui.px(18)), pady=ui.px(2)
                )
                ttk.Label(grid, text=value, style="Card.TLabel", wraplength=ui.px(480)).grid(
                    row=index, column=1, sticky="w", pady=ui.px(2)
                )
            ttk.Label(body, text=f"SHA-256 {row['sha256']}", style="Mono.TLabel").pack(
                anchor="w", pady=(ui.px(8), 0)
            )

    # ---------- advanced ----------

    def build_advanced(self, page):
        self.page_title(
            page,
            "Advanced",
            "Numbering, record files and recovery tools. Most labs never need to change these.",
        )
        ttk.Label(page, text="NUMBERING & RECORDS", style="Eyebrow.TLabel").pack(anchor="w")
        _, body = ui.card(page, fill="x", pady=(ui.px(6), ui.px(16)))
        self.setting_row(
            body,
            "Next ID number",
            "Can only move forward. Start a new counter file to restart numbering.",
            lambda parent: self.entry(parent, "counter_next", width=8),
        )
        self.setting_row(
            body,
            "ID digits",
            "Minimum digits, padded with zeros (3 → 001).",
            lambda parent: self.entry(parent, "counter_digits", width=4),
        )
        self.setting_row(
            body,
            "Counter file",
            "Empty = counter.json in the BaseMark folder. Keep it on a local disk.",
            lambda parent: self.entry(parent, "counter_file", width=28),
        )
        self.setting_row(
            body,
            "CSV log file",
            "Empty = log.csv in the BaseMark folder. Find part searches this file.",
            lambda parent: self.entry(parent, "log_file", width=28),
        )
        self.setting_row(
            body,
            "Material aliases",
            'JSON map from filament type to label, e.g. {"PET": "PETG"}.',
            lambda parent: self.entry(parent, "material_map", width=28),
            last=True,
        )

        ttk.Label(page, text="PRUSASLICER HOOK", style="Eyebrow.TLabel").pack(anchor="w")
        _, body = ui.card(page, fill="x", pady=(ui.px(6), ui.px(16)))
        ttk.Label(
            body,
            text="Set up PrusaSlicer on the Overview page does this for you. To do it by hand, "
            "paste this into Print Settings → Output options → Post-processing scripts and save "
            "the preset.",
            style="Card.Small.TLabel",
            wraplength=ui.px(620),
        ).pack(anchor="w", pady=(0, ui.px(8)))
        line = ttk.Frame(body, style="Card.TFrame")
        line.pack(fill="x")
        ttk.Entry(line, textvariable=self.hook, state="readonly", font=(ui.MONO, 9)).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(line, text="Copy", command=self.copy).pack(side="left", padx=(ui.px(8), 0))

        ttk.Label(page, text="TOOLS", style="Eyebrow.TLabel").pack(anchor="w")
        _, body = ui.card(page, fill="x", pady=(ui.px(6), ui.px(16)))
        self.setting_row(
            body,
            "Check a G-code file",
            "Tests an unstamped export with your settings. Changes nothing, uses no ID.",
            lambda parent: ttk.Button(parent, text="Choose file…", command=self.check_file),
        )
        self.setting_row(
            body,
            "Recover an interrupted export",
            "Select the surviving stamped file to finish its log entry and counter.",
            lambda parent: ttk.Button(parent, text="Choose file…", command=self.recover_file),
        )
        self.setting_row(
            body,
            "BaseMark folder",
            str(self.path.parent),
            lambda parent: ttk.Button(parent, text="Open folder", command=self.open_folder),
            last=True,
        )

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.hook.get())
        self.say("Command copied.", "ok")

    def open_folder(self):
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - opens the user's own data folder
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])

    def check_file(self):
        selected = filedialog.askopenfilename(
            parent=self.root, filetypes=[("G-code", "*.gcode"), ("All files", "*")]
        )
        if not selected:
            return
        from .service import process

        try:
            self.root.configure(cursor="watch")
            self.root.update_idletasks()
            outcome = process(Path(selected), self.path, {}, {}, dry_run=True)
            messagebox.showinfo("This file can be stamped", outcome.message, parent=self.root)
        except Exception as exc:
            messagebox.showwarning("This file would be skipped", str(exc), parent=self.root)
        finally:
            self.root.configure(cursor="")

    def recover_file(self):
        selected = filedialog.askopenfilename(
            parent=self.root, filetypes=[("G-code", "*.gcode"), ("All files", "*")]
        )
        if not selected:
            return
        try:
            settings = load_settings(self.path)
            validate_paths(self.path, settings, Path(selected))
            counter_path, _ = settings.paths(self.path.parent)
            with Counter(counter_path, settings.counter_next, recover=False) as counter:
                counter.recover_from(Path(selected))
                self.saved_next = counter.next
                self.values["counter_next"].set(str(counter.next))
            messagebox.showinfo(
                "Recovery complete",
                "Log entry recorded and counter advanced. The G-code file was not changed.",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("Recovery could not complete", str(exc), parent=self.root)

    # ---------- saving ----------

    def collect(self) -> Settings:
        data = asdict(self.settings)
        for key, variable in self.values.items():
            value = variable.get()
            if key in INTEGER_FIELDS:
                value = int(str(value).strip())
            elif key in FLOAT_FIELDS:
                value = float(str(value).strip())
            elif key == "material_map":
                value = json.loads(value)
            elif isinstance(value, str):
                value = value.strip()
            data[key] = value
        return Settings(**data).validate()

    def save(self):
        """Validate and save every field; called automatically after each change."""
        try:
            settings = self.collect()
            if settings == self.settings and settings.counter_next == self.saved_next:
                self.refresh_overview()
                return
            counter_path, _ = settings.paths(self.path.parent)
            validate_paths(self.path, settings)
            with Counter(counter_path) as counter:
                if settings.counter_next < counter.next:
                    raise ValueError(
                        f"Next ID must be at least {counter.next}; it cannot go backwards."
                    )
                save_settings(self.path, settings)
                counter.reset(settings.counter_next)
                self.saved_next = counter.next
            self.settings = settings
            self.say("Saved. Applies to your next export.", "ok")
        except json.JSONDecodeError:
            self.say('Material aliases must be JSON, e.g. {"PET": "PETG"}. Not saved.', "bad")
        except Exception as exc:
            self.say(f"Not saved: {exc}", "bad")
        self.refresh_overview()


def open_settings(path: Path):
    ui.enable_dpi_awareness()
    root = tk.Tk()
    try:
        SettingsWindow(root, path)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
