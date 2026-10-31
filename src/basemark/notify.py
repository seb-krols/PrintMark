"""A small corner notice after each export, so a skipped stamp is never silent.

PrusaSlicer only shows a post-processing script's output when the script fails, and
BaseMark deliberately exits 0 on a safe skip. The notice runs in its own detached
process: the export finishes immediately and never waits for it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .licensing import LIMIT_REACHED

USER_SKIP = "Label skipped; file unchanged, no ID consumed."
UNSTAMPED = "unstamped"  # the background check found an export BaseMark never saw
UNSTAMPED_UPLOAD = "unstamped-upload"  # ... or a job sent to a printer without BaseMark
SECONDS = {"stamped": 6, "stamped-pending-audit": 20, UNSTAMPED: 30, UNSTAMPED_UPLOAD: 30}


def wanted(outcome) -> bool:
    if outcome.status in {"disabled", "preview"}:
        return False
    # The operator chose Skip in the export window; telling them again is noise.
    return not (outcome.status == "skipped" and outcome.message == USER_SKIP)


def launcher(module: str) -> list[str]:
    """Windowed command for a BaseMark entry point (the installed desktop exe when frozen)."""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return [str(executable.with_name("basemark-desktop.exe"))]
    windowed = executable.with_name("pythonw.exe")  # no console flash on Windows
    return [str(windowed if windowed.is_file() else executable), "-m", module]


def command(config: Path, status: str, message: str, source: str) -> list[str]:
    tail = ["--notify", status, message, source, "--config", str(config)]
    return [*launcher("basemark.notify"), *tail]


def spawn(config: Path, status: str, message: str, source: str) -> None:
    """Start the notice without holding PrusaSlicer's output pipes open."""
    options = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    args = command(config, status, message, source)
    if sys.platform != "win32":
        subprocess.Popen(args, start_new_session=True, **options)
        return
    detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        # Leave the slicer's job object, if any, so the notice outlives the hook.
        subprocess.Popen(args, creationflags=detached | 0x01000000, **options)
    except OSError:
        subprocess.Popen(args, creationflags=detached, **options)


def announce(config: Path, outcome, overrides: dict, source: Path | str) -> None:
    """Show the export result if enabled. Never raises: the export already succeeded."""
    try:
        from .config import load_settings

        try:
            if not load_settings(config, overrides=overrides).notify:
                return
        except Exception:
            pass  # an invalid config is exactly what the operator must hear about
        if wanted(outcome):
            spawn(config, outcome.status, outcome.message, str(source))
    except Exception:
        pass


def destination(env: dict[str, str], source: Path | str) -> str:
    """The name shown for an export: the target file, plus the printer host it is sent to."""
    name = env.get("SLIC3R_PP_OUTPUT_NAME") or str(source)
    host = env.get("SLIC3R_PP_HOST", "File")
    if host and host != "File":  # "OctoPrint", "PrusaLink", "PrusaConnect", ...
        return f"{Path(name).name} (sent to {host})"
    return name


def texts(status: str, message: str) -> tuple[str, str, str]:
    """(tone, title, body) for a status written by the export."""
    if status == "stamped":
        label = message.removeprefix("Stamped ").split(" · ")[0]
        details = message.split(" · ")[1:]
        detail = " · ".join(details).rstrip(".")
        if details and " of " in details[0]:  # "2 of 3 parts": some parts got no label
            stamped, _, total = details[0].removesuffix(" parts").partition(" of ")
            missing = int(total) - int(stamped)
            rest = " · ".join(details[1:]).rstrip(".")
            note = (
                f"{missing} part{'s' if missing != 1 else ''} got no label (no room, or left out)."
            )
            return "warn", f"Stamped {label} on {details[0]}", f"{note}\n{rest}"
        return "ok", f"Stamped {label}", detail
    if status in (UNSTAMPED, UNSTAMPED_UPLOAD):
        title = "Exported" if status == UNSTAMPED else "Sent to the printer"
        return (
            "warn",
            f"{title} without BaseMark",
            f"{message}\nTurn this warning off in BaseMark → Overview.",
        )
    if status == "stamped-pending-audit":
        return "warn", "Stamped — record needs recovery", message
    reason = message.removeprefix("skipped — ")
    if reason.startswith(LIMIT_REACHED):
        return (
            "warn",
            "Free monthly limit reached",
            f"{reason[:1].upper()}{reason[1:]}\nThe G-code was exported unchanged.",
        )
    return (
        "bad" if status == "error" else "warn",
        "Export not stamped",
        f"{reason[:1].upper()}{reason[1:]}\nThe G-code was exported unchanged; no ID was used.",
    )


def show(status: str, message: str, source: str, config: Path, *, seconds=None, root=None):
    import tkinter as tk

    from . import ui_common as ui

    own = root is None
    if own:
        ui.enable_dpi_awareness()
        root = tk.Tk()
    ui.style(root)
    tone, title, body = texts(status, message)
    colour = {"ok": ui.ACCENT, "warn": ui.WARN, "bad": ui.DANGER}[tone]
    soft = {"ok": ui.ACCENT_SOFT, "warn": ui.WARN_SOFT, "bad": ui.DANGER_SOFT}[tone]
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(background=ui.LINE)
    px = ui.px
    frame = tk.Frame(root, background=ui.PANEL, padx=px(14), pady=px(12))
    frame.pack(fill="both", expand=True, padx=1, pady=1)
    tk.Frame(frame, background=colour, width=px(4)).pack(side="left", fill="y", padx=(0, px(12)))
    icon = {"ok": "✓", "warn": "!", "bad": "✕"}[tone]
    tk.Label(
        frame, text=icon, font=(ui.SEMIBOLD, 13), foreground=colour, background=soft, width=2
    ).pack(side="left", anchor="n", padx=(0, px(12)))
    words = tk.Frame(frame, background=ui.PANEL)
    words.pack(side="left", fill="both", expand=True)
    head = tk.Frame(words, background=ui.PANEL)
    head.pack(fill="x")
    tk.Label(
        head, text="BASEMARK", font=(ui.SEMIBOLD, 8), foreground=ui.SUBTLE, background=ui.PANEL
    ).pack(side="left")
    close = tk.Label(
        head, text="✕", font=(ui.FONT, 9), foreground=ui.SUBTLE, background=ui.PANEL, cursor="hand2"
    )
    close.pack(side="right")
    tk.Label(
        words,
        text=title,
        font=(ui.SEMIBOLD, 12),
        foreground=ui.INK,
        background=ui.PANEL,
        anchor="w",
        justify="left",
    ).pack(fill="x", pady=(px(2), 0))
    name = Path(source).name if source else ""
    tk.Label(
        words,
        text="\n".join(filter(None, [body, name])),
        font=(ui.FONT, 9),
        foreground=ui.MUTED,
        background=ui.PANEL,
        anchor="w",
        justify="left",
        wraplength=px(300),
    ).pack(fill="x", pady=(px(2), px(8)))
    link = tk.Label(
        words,
        text="Open BaseMark",
        font=(ui.SEMIBOLD, 9),
        foreground=ui.ACCENT,
        background=ui.PANEL,
        cursor="hand2",
    )
    link.pack(anchor="w")

    state = {"timer": None}

    def dismiss(_=None):
        try:
            root.destroy() if own else root.withdraw()
        except tk.TclError:
            pass

    def open_app(_=None):
        try:
            extra = [] if getattr(sys, "frozen", False) else ["--settings"]
            subprocess.Popen([*launcher("basemark"), *extra, "--config", str(config)])
        finally:
            dismiss()

    def arm(_=None):
        if state["timer"]:
            root.after_cancel(state["timer"])
        state["timer"] = root.after(int(seconds * 1000), dismiss)

    def hold(_=None):  # keep it while the pointer is over the notice
        if state["timer"]:
            root.after_cancel(state["timer"])
            state["timer"] = None

    seconds = seconds or SECONDS.get(status, 15)
    close.bind("<Button-1>", dismiss)
    link.bind("<Button-1>", open_app)
    root.bind("<Enter>", hold)
    root.bind("<Leave>", arm)
    root.update_idletasks()
    width = px(380)
    height = root.winfo_reqheight()
    left, top, area_width, area_height = ui.work_area(root)
    margin = px(16)
    x = left + area_width - width - margin
    y = top + area_height - height - margin
    root.geometry(f"{width}x{height}+{x}+{y}")
    arm()
    if own:
        root.mainloop()
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BaseMark export notice")
    parser.add_argument("--notify", nargs=3, metavar=("STATUS", "MESSAGE", "SOURCE"))
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        show(*args.notify, args.config)
    except Exception:
        return 1  # no display, or the user logged off: nothing useful to report
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
