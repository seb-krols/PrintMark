"""Background check: warn when PrusaSlicer exports or sends a file that BaseMark never saw.

BaseMark only runs from print presets that list it as a post-processing script, so an
export from any other preset is unstamped without a word. This small windowless process
(started at login by the Windows installer) looks for new G-code files in PrusaSlicer's
export folders, and for the temporary copy PrusaSlicer makes when it sends a job to a
printer (OctoPrint, PrusaLink, ...), and shows a notice for each one made without BaseMark.
It reads only the start and end of new files and never changes them.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

from .config import config_dir, load_settings
from .prusaslicer import data_dir, read_ini

POLL_SECONDS = 2
UPLOAD_SECONDS = 0.5  # temp folder look without change notifications (not Windows)
TAIL_BYTES = 512 * 1024  # PrusaSlicer writes its settings at the end of the file
STATUS = "unstamped"
UPLOAD_STATUS = "unstamped-upload"
# Send to printer: PrusaSlicer copies the G-code to %TEMP%\.PrusaSlicer.upload.xxxx-xxxx-...,
# runs the post-processing scripts on it, uploads it and deletes it.
UPLOAD_NAME = re.compile(r"^\.PrusaSlicer[^.]*\.upload\.", re.IGNORECASE)
BINARY_GRACE = 3  # seconds for a hooked BaseMark to report a binary upload itself
PENDING = "pending"  # an upload copy that is still being written
BINARY = (
    "It is binary G-code (.bgcode), which BaseMark cannot stamp. Select the “+ BaseMark” "
    "printer preset in PrusaSlicer: it makes plain G-code."
)


def lock_path(config: Path) -> Path:
    return config.parent / "watcher.lock"


def stop_path(config: Path) -> Path:
    return config.parent / "watcher.stop"


def export_folders(data: Path | None) -> list[Path]:
    """Where exports land: PrusaSlicer's last export folders, Downloads and Desktop."""
    folders = []
    if data is not None:
        try:
            app = read_ini(data / "PrusaSlicer.ini").get("", {})
        except OSError:
            app = {}
        for key in ("last_output_path", "last_output_path_removable"):
            if app.get(key):
                folders.append(Path(app[key]))
    folders += [Path.home() / "Downloads", Path.home() / "Desktop"]
    unique = {}
    for folder in folders:
        unique.setdefault(os.path.normcase(os.path.abspath(folder)), folder)
    return [folder for folder in unique.values() if folder.is_dir()]


def temp_folder() -> Path:
    """The folder PrusaSlicer stages uploads in (Boost's temp_directory_path: TMP first)."""
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetTempPathW(len(buffer), buffer):
            return Path(buffer.value)
    return Path(tempfile.gettempdir())


def open_shared(path: Path):
    """Open for reading without stopping PrusaSlicer from deleting the file meanwhile."""
    if sys.platform != "win32":
        return path.open("rb")
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    # GENERIC_READ; share read, write and delete; OPEN_EXISTING; FILE_ATTRIBUTE_NORMAL
    handle = create(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY), "rb")


def report_time(config: Path) -> float | None:
    try:
        report = json.loads((config.parent / "last-export.json").read_text(encoding="utf-8"))
        return datetime.fromisoformat(report["timestamp"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def reported_by_basemark(config: Path, path: Path, now: float) -> bool:
    """BaseMark ran on this export and already showed its own notice."""
    try:
        report = json.loads((config.parent / "last-export.json").read_text(encoding="utf-8"))
        moment = datetime.fromisoformat(report["timestamp"]).timestamp()
        source = Path(str(report.get("source", ""))).name
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return source.lower() == path.name.lower() and abs(now - moment) < 600


def inspect(path: Path, *, upload: bool = False) -> str | None:
    """Why BaseMark did not see this file, or None if it did (or it isn't PrusaSlicer's).

    For an upload copy, PENDING means PrusaSlicer is still writing it: look again soon.
    """
    with open_shared(path) as stream:
        head = stream.read(4096)
        if upload or path.suffix.lower() == ".bgcode":
            if head.startswith(b"GCDE"):
                return BINARY
            if not upload:
                return None
        if upload and not head:
            return PENDING
        if head.startswith(b"; BASEMARK stamp") or b"generated by PrusaSlicer" not in head:
            return None
        size = stream.seek(0, os.SEEK_END)
        stream.seek(max(0, size - TAIL_BYTES))
        tail = stream.read()
    if upload and b"; prusaslicer_config = end" not in tail:
        return PENDING
    hook = re.search(rb"^; post_process = (.*)$", tail, re.MULTILINE)
    if hook is None or b"basemark" in hook[1].lower():
        return None  # unknown layout, or BaseMark ran and reported the result itself
    preset = re.search(rb"^; print_settings_id = (.*)$", tail, re.MULTILINE)
    name = preset[1].decode("utf-8", "replace").strip() if preset else ""
    where = f"Print preset “{name}”" if name else "The print preset"
    return (
        f"{where} doesn't run BaseMark, so this part has no label. In PrusaSlicer, select a "
        "“… + BaseMark” print preset, or set this one up in BaseMark (Overview)."
    )


class Watcher:
    """One look per tick at the export folders; a file is read once it stops changing.

    Upload copies are short-lived, so tick_uploads() reads them as soon as they appear.
    """

    def __init__(self, config: Path, *, started: float | None = None, data=None, temp=None):
        self.config = config
        self.started = time.time() if started is None else started
        self.data = data
        self.temp = temp_folder() if temp is None else temp
        self.uploads: set[str] = set()  # upload copies already decided
        self.binary: dict[str, float] = {}  # binary upload -> creation time, awaiting a report
        self.copying = False  # an upload copy was still being written at the last look
        self.folders: list[Path] = []
        self.folder_key = object()
        self.settings_key = object()
        self.enabled = True
        self.pending: dict[str, tuple[int, int]] = {}  # path -> (mtime_ns, size) last tick
        self.done: dict[str, int] = {}  # path -> mtime_ns already checked

    def refresh(self):
        try:
            key = self.config.stat().st_mtime_ns
        except OSError:
            key = None
        if key != self.settings_key:
            self.settings_key = key
            try:
                self.enabled = load_settings(self.config).warn_unstamped
            except Exception:
                self.enabled = True  # an unreadable config must not silence the warning
        data = self.data if self.data is not None else data_dir()
        try:
            key = (data, (data / "PrusaSlicer.ini").stat().st_mtime_ns if data else None)
        except OSError:
            key = (data, None)
        if key != self.folder_key:
            self.folder_key = key
            self.folders = export_folders(data)

    def tick(self, now: float | None = None) -> list[tuple[Path, str]]:
        """Check the folders once; returns the unstamped exports found (and notifies)."""
        self.refresh()
        if not self.enabled:
            self.pending.clear()
            return []
        now = time.time() if now is None else now
        found, waiting = [], {}
        for folder in self.folders:
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                if not entry.name.lower().endswith((".gcode", ".bgcode")):
                    continue
                try:
                    info = os.stat(entry.path)
                except OSError:
                    continue
                if info.st_mtime < self.started or self.done.get(entry.path) == info.st_mtime_ns:
                    continue
                state = (info.st_mtime_ns, info.st_size)
                if self.pending.get(entry.path) != state:
                    waiting[entry.path] = state  # new or still being written
                    continue
                self.done[entry.path] = info.st_mtime_ns
                path = Path(entry.path)
                try:
                    reason = inspect(path)
                except OSError:
                    continue
                if reason and not reported_by_basemark(self.config, path, now):
                    found.append((path, reason))
        self.pending = waiting
        for path, reason in found:
            self.notify(path, reason)
        return found

    def tick_uploads(self, now: float | None = None) -> list[tuple[Path, str]]:
        """Check PrusaSlicer's upload copies once; returns the ones made without BaseMark."""
        if not self.enabled:
            return []
        now = time.time() if now is None else now
        found, present, copying = [], set(), False
        try:
            entries = [e for e in os.scandir(self.temp) if UPLOAD_NAME.match(e.name)]
        except OSError:
            entries = []
        for entry in entries:
            present.add(entry.path)
            if entry.path in self.uploads:
                continue
            try:
                info = os.stat(entry.path)
            except OSError:
                continue  # uploaded and deleted just now
            born = getattr(info, "st_birthtime", info.st_ctime)
            if born < self.started - 5:  # left behind by an upload before this check ran
                self.uploads.add(entry.path)
                continue
            try:
                reason = inspect(Path(entry.path), upload=True)
            except OSError:
                reason = PENDING  # not readable yet
            if reason == PENDING:
                if now - born > 10:
                    self.uploads.add(entry.path)  # never finished (slicer closed?): stop looking
                else:
                    copying = True
                continue
            self.uploads.add(entry.path)
            if reason == BINARY:
                self.binary[entry.path] = born  # a hooked BaseMark skips it and says so
            elif reason:
                found.append((Path(entry.path), reason))
        for path, born in list(self.binary.items()):
            if now - born >= BINARY_GRACE:
                del self.binary[path]
                reported = report_time(self.config)
                if reported is None or reported < born - 1:
                    found.append((Path(path), BINARY))
        self.uploads &= present  # uploaded and deleted: forget it
        self.copying = copying  # look again soon: no notification comes as it grows
        for path, reason in found:
            self.notify(path, reason, upload=True)
        return found

    def notify(self, path: Path, reason: str, *, upload: bool = False):
        from .notify import spawn

        try:
            if upload:  # the copy's name means nothing to anyone; the reason names the preset
                spawn(self.config, UPLOAD_STATUS, reason, "")
            else:
                spawn(self.config, STATUS, reason, str(path))
        except OSError:
            pass


SLICERS = {"prusa-slicer.exe", "prusa-slicer-console.exe"}
IDLE_SECONDS = 5  # PrusaSlicer closed: how often to see whether it has started
QUIET_SECONDS = 60  # PrusaSlicer open and nothing happening: longest sleep
NAMES, SIZES, WRITES = 0x1, 0x8, 0x10  # FILE_NOTIFY_CHANGE_* flags


def slicer_pids() -> list[int]:
    """Running PrusaSlicer processes, from a cheap process snapshot (Windows only)."""
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, ctypes.c_void_p(-1).value):
        return []
    found = []
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = kernel.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() in SLICERS:
                found.append(entry.th32ProcessID)
            more = kernel.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        kernel.CloseHandle(ctypes.c_void_p(snapshot))
    return found


class Signals:
    """Windows objects the check sleeps on: folder changes and PrusaSlicer's process.

    The check uses no processor time while it waits; Windows wakes it when a file appears
    in a watched folder, when PrusaSlicer exits, or when the timeout ends.
    """

    def __init__(self):
        self.items: list[tuple[str, int, bool]] = []  # (key, handle, is_folder)
        self.last = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def folder(self, key: str, path: Path, flags: int) -> None:
        kernel = ctypes.windll.kernel32
        kernel.FindFirstChangeNotificationW.restype = ctypes.c_void_p
        handle = kernel.FindFirstChangeNotificationW(str(path), False, flags)
        if handle not in (None, ctypes.c_void_p(-1).value):
            self.items.append((key, handle, True))

    def process(self, pid: int) -> bool:
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if handle:
            self.items.append(("slicer", handle, False))
        return bool(handle)

    def wait(self, seconds: float) -> set[str]:
        """Sleep until something happens or the time is up; the keys that fired."""
        kernel = ctypes.windll.kernel32
        if self.items:
            handles = (ctypes.c_void_p * len(self.items))(*(h for _, h, _ in self.items))
            kernel.WaitForMultipleObjects(len(self.items), handles, False, int(seconds * 1000))
        else:
            time.sleep(seconds)
        fired = set()
        for key, handle, is_folder in self.items:
            if kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0:
                fired.add(key)
                if is_folder:
                    kernel.FindNextChangeNotification(ctypes.c_void_p(handle))
        # A busy temp folder must not turn into a busy loop.
        pause = 0.1 - (time.monotonic() - self.last)
        if pause > 0:
            time.sleep(pause)
        self.last = time.monotonic()
        return fired

    def close(self) -> None:
        kernel = ctypes.windll.kernel32
        for _, handle, is_folder in self.items:
            close = kernel.FindCloseChangeNotification if is_folder else kernel.CloseHandle
            close(ctypes.c_void_p(handle))
        self.items = []


def settled(watcher: Watcher) -> bool:
    """No export or upload is half-seen, so nothing needs another look."""
    return not (watcher.pending or watcher.copying or watcher.binary)


def safely(check) -> None:
    try:
        check()
    except Exception:
        pass  # a passing file-system error must not end the watch


def watch_windows(watcher: Watcher, config: Path, poll: float) -> None:
    """Event-driven loop: asleep while PrusaSlicer is closed, woken by Windows when open."""
    stopping = stop_path(config).exists
    while not stopping():
        pids = slicer_pids()
        if not pids and settled(watcher):
            # Nothing can be exported or sent while PrusaSlicer is closed.
            with Signals() as signals:
                signals.folder("config", config.parent, NAMES | WRITES)  # stop request
                signals.wait(IDLE_SECONDS)
            continue
        safely(watcher.refresh)
        folders = list(watcher.folders)
        with Signals() as signals:
            signals.folder("config", config.parent, NAMES | WRITES)
            signals.folder("temp", watcher.temp, NAMES)
            for folder in folders:
                signals.folder("exports", folder, NAMES | SIZES | WRITES)
            followed = all([signals.process(pid) for pid in pids])
            safely(watcher.tick)
            safely(watcher.tick_uploads)
            while not stopping():
                if watcher.copying:
                    timeout = 0.1
                elif not settled(watcher):
                    timeout = poll
                else:
                    timeout = QUIET_SECONDS if followed else IDLE_SECONDS
                fired = signals.wait(timeout)
                if "temp" in fired or not settled(watcher):
                    safely(watcher.tick_uploads)
                if fired & {"exports", "config"} or not fired or not settled(watcher):
                    safely(watcher.tick)  # also reads the on/off setting
                if "slicer" in fired or watcher.folders != folders:
                    break  # PrusaSlicer closed, or exports go elsewhere now
                if not followed and slicer_pids() != pids:
                    break
                if not pids and settled(watcher):
                    break


def running(config: Path) -> bool:
    try:
        with FileLock(str(lock_path(config)), timeout=0):
            return False
    except Timeout:
        return True


def run(config: Path, poll: float = POLL_SECONDS) -> int:
    """The background loop. Exits at once if another copy is already watching."""
    config.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path(config)), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        return 0
    try:
        stop_path(config).unlink(missing_ok=True)
        watcher = Watcher(config)
        if sys.platform == "win32":
            watch_windows(watcher, config, poll)
        else:
            while not stop_path(config).exists():
                safely(watcher.tick)
                for _ in range(max(1, int(poll / UPLOAD_SECONDS))):
                    safely(watcher.tick_uploads)
                    time.sleep(0.1 if watcher.copying else UPLOAD_SECONDS)
        stop_path(config).unlink(missing_ok=True)
        return 0
    finally:
        lock.release()


def stop(config: Path, wait: float = 8) -> bool:
    """Ask a running watcher to exit (installer, uninstaller). True once it has."""
    if not running(config):
        return True
    stop_path(config).parent.mkdir(parents=True, exist_ok=True)
    stop_path(config).touch()
    deadline = time.time() + wait
    while time.time() < deadline:
        if not running(config):
            return True
        time.sleep(0.25)
    return False


def ensure_running(config: Path) -> None:
    """Start the installed watcher if it should run and doesn't (e.g. right after setup)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return  # source installs start it by hand: basemark --watch
    try:
        if not load_settings(config).warn_unstamped or running(config):
            return
        from .notify import launcher

        args = [*launcher("basemark"), "--watch", "--config", str(config)]
        detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            args,
            creationflags=detached,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BaseMark export check")
    parser.add_argument("--config", type=Path, default=config_dir() / "config.toml")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)
    if args.stop:
        return 0 if stop(args.config) else 1
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
