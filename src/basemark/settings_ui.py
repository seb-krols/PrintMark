from __future__ import annotations

import json
import sys
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .audit import format_records, lookup_id
from .config import Settings, config_dir, load_settings, save_settings, validate_paths
from .counter import Counter
from .diagnostics import read_report
from .ui_common import ACCENT, FONT, MUTED, brand, center, style


class SettingsWindow:
    def __init__(self, root, path: Path):
        self.root, self.path = root, path
        self.settings = load_settings(path)
        self.values = {}
        root.title("BaseMark · Lab settings")
        root.minsize(720, 650)
        style(root)
        brand(
            root,
            "LAB SETTINGS",
            "Material identity, printed in.",
            "Set it once. Every export carries your lab’s material and part ID.",
        )
        # Reserve actions before the expanding notebook, including on small screens.
        footer = ttk.Frame(root)
        footer.pack(side="bottom", fill="x", padx=28, pady=18)
        self.feedback = ttk.Label(footer, text="Settings stay on this computer.", foreground=MUTED)
        self.feedback.pack(side="left")
        ttk.Button(footer, text="Save settings  →", style="Accent.TButton", command=self.save).pack(
            side="right"
        )
        ttk.Button(footer, text="Close", command=root.destroy).pack(side="right", padx=10)
        ttk.Separator(root).pack(side="bottom", fill="x")
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=28, pady=(4, 20))
        general, identity, integration, diagnostics, records = (
            ttk.Frame(notebook, padding=20) for _ in range(5)
        )
        for name, panel in [
            ("Stamp", general),
            ("Identity & records", identity),
            ("PrusaSlicer setup", integration),
            ("Diagnostics", diagnostics),
            ("Find part", records),
        ]:
            notebook.add(panel, text=name)
            panel.columnconfigure(1, weight=1)
        self.values["enabled"] = tk.BooleanVar(value=self.settings.enabled)
        ttk.Checkbutton(
            general, text="Stamp exported prints", variable=self.values["enabled"]
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))
        self.field(general, 1, "mode", "Placement mode", choices=["interactive", "auto"])
        self.field(general, 2, "text_height_mm", "Text height (mm)")
        self.field(general, 3, "min_text_height_mm", "Smallest text (mm)")
        self.field(general, 4, "layers", "Depth (layers)", choices=["1", "2", "3"])
        self.field(general, 5, "margin_mm", "Edge margin (mm)")
        self.field(general, 6, "template", "Label template")
        ttk.Label(
            general,
            text="Available: {material}, {id}, {date}, {prefix}\n"
            "Keep {material} and {id}. The ID already includes your computer prefix.",
            foreground=MUTED,
            wraplength=560,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.field(identity, 0, "counter_prefix", "Computer prefix")
        self.field(identity, 1, "counter_digits", "ID digits")
        counter_path, _ = self.settings.paths(path.parent)
        validate_paths(path, self.settings)
        with Counter(counter_path, self.settings.counter_next, recover=False) as counter:
            next_value = counter.next
        self.field(identity, 2, "counter_next", "Next ID number")
        self.values["counter_next"].set(str(next_value))
        self.field(identity, 3, "counter_file", "Counter file")
        self.field(identity, 4, "log_file", "CSV log file")
        self.field(identity, 5, "material_map", "Material aliases (JSON)")
        self.values["material_map"].set(json.dumps(self.settings.material_map))
        ttk.Label(
            identity,
            text="Use a unique prefix for each PC, such as A or B.\n"
            "Empty file paths use this config folder. Keep counters on a local disk.\n"
            "The counter can move forward; start a new counter file to restart numbering.",
            foreground=MUTED,
            wraplength=580,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self.integration(integration)
        self.diagnostics(diagnostics)
        self.records(records)
        center(root, 860, 760)

    def records(self, panel):
        ttk.Label(panel, text="Find a printed part", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text="Enter the complete ID, including the PC prefix and leading zeros.\n"
            "Searches the CSV in your saved settings. This does not consume an ID.",
            foreground=MUTED,
        ).pack(anchor="w", pady=(8, 16))
        row = ttk.Frame(panel)
        row.pack(fill="x")
        self.lookup_value = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.lookup_value)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _: self.find_part())
        ttk.Button(row, text="Find part", command=self.find_part).pack(side="right", padx=(10, 0))
        result = ttk.Frame(panel)
        result.pack(fill="both", expand=True, pady=(16, 0))
        self.lookup_result = tk.Text(
            result, height=12, width=50, wrap="word", font=(FONT, 10), state="disabled"
        )
        scroll = ttk.Scrollbar(result, orient="vertical", command=self.lookup_result.yview)
        scroll.pack(side="right", fill="y")
        self.lookup_result.configure(yscrollcommand=scroll.set)
        self.lookup_result.pack(side="left", fill="both", expand=True)

    def find_part(self):
        try:
            settings = load_settings(self.path)
            _, log = settings.paths(self.path.parent)
            result = format_records(lookup_id(log, self.lookup_value.get()))
        except Exception as exc:
            result = f"Could not search the log: {exc}"
        self.lookup_result.configure(state="normal")
        self.lookup_result.delete("1.0", "end")
        self.lookup_result.insert("1.0", result)
        self.lookup_result.configure(state="disabled")

    def field(self, parent, row, key, label, choices=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 25), pady=9)
        variable = tk.StringVar(value=str(getattr(self.settings, key)))
        self.values[key] = variable
        if choices:
            entry = ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly")
        else:
            entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=9)

    def integration(self, panel):
        ttk.Label(panel, text="01 / Choose plain G-code", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text="In PrusaSlicer, use Expert mode and turn off binary G-code.\n"
            "Disable arc fitting for this first release.",
            foreground=MUTED,
        ).pack(anchor="w", pady=(7, 22))
        ttk.Label(panel, text="02 / Connect the post-processor", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            panel,
            text="Print Settings → Output options → Post-processing scripts",
            foreground=MUTED,
        ).pack(anchor="w", pady=(7, 10))
        executable = Path(sys.executable)
        if getattr(sys, "frozen", False) and executable.name.lower() == "basemark-desktop.exe":
            executable = executable.with_name("basemark.exe")
        command = (
            f'"{executable}"' if getattr(sys, "frozen", False) else f'"{executable}" -m basemark'
        )
        if self.path != config_dir() / "config.toml":
            command += f' --config "{self.path}"'
        self.hook = tk.StringVar(value=command)
        ttk.Entry(panel, textvariable=self.hook, state="readonly").pack(fill="x")
        ttk.Button(panel, text="Copy command", command=self.copy).pack(anchor="w", pady=10)
        ttk.Label(panel, text="03 / Try a small coupon", style="Heading.TLabel").pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Label(
            panel,
            text="Export, place the stamp, then inspect the exported file in G-code Viewer.\n"
            "Validate readability and adhesion on your lab’s sheets before wider use.",
            foreground=MUTED,
        ).pack(anchor="w", pady=(7, 20))
        ttk.Label(
            panel,
            text=f"CONFIG FILE\n{self.path}",
            foreground=ACCENT,
            wraplength=650,
            font=(FONT, 9),
        ).pack(anchor="w")

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.hook.get())
        self.feedback.configure(text="PrusaSlicer command copied.", foreground=ACCENT)

    def diagnostics(self, panel):
        ttk.Label(panel, text="Last export", style="Heading.TLabel").pack(anchor="w")
        report = ttk.Frame(panel)
        report.pack(fill="x", pady=(8, 8))
        self.last_export = tk.Text(report, height=4, width=50, wrap="word", font=(FONT, 9))
        scroll = ttk.Scrollbar(report, orient="vertical", command=self.last_export.yview)
        scroll.pack(side="right", fill="y")
        self.last_export.configure(yscrollcommand=scroll.set)
        self.last_export.pack(side="left", fill="x", expand=True)
        self.refresh_report()
        ttk.Button(panel, text="Refresh result", command=self.refresh_report).pack(anchor="w")
        ttk.Separator(panel).pack(fill="x", pady=10)
        ttk.Label(panel, text="Check a profile without printing", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            panel,
            text="Choose an unstamped PrusaSlicer export. Uses your saved settings.\n"
            "This check does not edit G-code or consume an ID.",
            foreground=MUTED,
        ).pack(anchor="w", pady=8)
        ttk.Button(panel, text="Check G-code…", command=self.check_file).pack(anchor="w")
        ttk.Separator(panel).pack(fill="x", pady=10)
        ttk.Label(panel, text="Recover an interrupted export", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            panel,
            text="If the temporary file is gone, select the surviving stamped export.\n"
            "Recovery requires an exact content match and never modifies the selected file.",
            foreground=MUTED,
        ).pack(anchor="w", pady=8)
        ttk.Button(panel, text="Recover from exported G-code…", command=self.recover_file).pack(
            anchor="w"
        )

    def refresh_report(self):
        self.last_export.configure(state="normal")
        self.last_export.delete("1.0", "end")
        self.last_export.insert("1.0", read_report(self.path))
        self.last_export.configure(state="disabled")

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
            messagebox.showinfo("Profile check", outcome.message, parent=self.root)
        except Exception as exc:
            messagebox.showwarning("Profile would be skipped", str(exc), parent=self.root)
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
                self.values["counter_next"].set(str(counter.next))
            messagebox.showinfo(
                "Recovery complete",
                "Audit recorded and counter advanced. G-code was not changed.",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("Recovery could not complete", str(exc), parent=self.root)

    def save(self):
        try:
            data = asdict(self.settings)
            for key, variable in self.values.items():
                value = variable.get()
                if key in {"layers", "counter_digits", "counter_next"}:
                    value = int(value)
                elif key in {"text_height_mm", "min_text_height_mm", "margin_mm"}:
                    value = float(value)
                elif key == "material_map":
                    value = json.loads(value)
                data[key] = value
            settings = Settings(**data).validate()
            counter_path, log_path = settings.paths(self.path.parent)
            validate_paths(self.path, settings)
            with Counter(counter_path) as counter:
                if settings.counter_next < counter.next:
                    raise ValueError(
                        f"Next ID must be at least {counter.next}; it cannot go backwards."
                    )
                save_settings(self.path, settings)
                counter.reset(settings.counter_next)
            self.settings = settings
            self.feedback.configure(text="Saved. Applies to your next export.", foreground=ACCENT)
        except Exception as exc:
            messagebox.showerror("Settings could not be saved", str(exc), parent=self.root)


def open_settings(path: Path):
    root = tk.Tk()
    try:
        SettingsWindow(root, path)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
