"""Local counter and audit log with an explicit, recoverable file-write journal.

One lock serializes a workstation's exports, including the interactive decision.
The journal is persisted BEFORE the G-code replacement. The counter advances
AFTER it. Recovery compares hashes and never blindly reuses an uncertain ID.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from .audit import LOG_FIELDS, read_log
from .config import atomic_write
from .errors import SafeSkip


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Counter:
    def __init__(self, path: Path, minimum: int = 1, *, recover: bool = True):
        self.path = path
        self.minimum = minimum
        self.auto_recover = recover
        self.lock = FileLock(str(path) + ".lock", timeout=0.25)
        self.state = {"next": minimum, "pending": None}
        self.audit_locks = {}

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock.acquire()
        except Timeout as exc:
            raise SafeSkip(
                "another export/settings window is using this counter; try again"
            ) from exc
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
                if type(self.state.get("next")) is not int or self.state["next"] < 1:
                    raise SafeSkip("counter state is invalid; restore its backup")
            if self.auto_recover:
                self.recover()
            self.state["next"] = max(self.minimum, self.state["next"])
        except BaseException:
            self.lock.release()
            raise
        return self

    def __exit__(self, *_):
        self.lock.release()

    @property
    def next(self):
        return self.state["next"]

    def save(self):
        atomic_write(self.path, json.dumps(self.state, indent=2).encode("utf-8"))

    def recover(self):
        pending = self.state.get("pending")
        if not pending:
            return
        target = Path(pending["target"])
        if not target.exists():
            # PrusaSlicer may already have copied and deleted its temporary file.
            # Only an absolute final path AND the exact committed hash are evidence.
            final = Path(pending["row"].get("gcode_filename", ""))
            if (
                final.is_absolute()
                and final.is_file()
                and digest(final.read_bytes()) == pending["after"]
            ):
                self.finish()
                return
            raise SafeSkip(
                f"interrupted export needs review: {target} is missing; see docs/recovery.md"
            )
        current = digest(target.read_bytes())
        if current == pending["after"]:
            self.finish()
        elif current == pending["before"]:
            self.state["pending"] = None
            self.save()
        else:
            raise SafeSkip("interrupted export changed externally; see docs/recovery.md")

    def recover_from(self, candidate: Path):
        pending = self.state.get("pending")
        if not pending:
            raise SafeSkip("no interrupted export is waiting for recovery")
        if digest(candidate.read_bytes()) != pending["after"]:
            raise SafeSkip(
                "selected file does not match the stamped output; recovery was not changed"
            )
        # Persist the new location before committing, so another interruption can recover.
        pending["target"] = str(candidate.resolve())
        self.save()
        self.finish()

    def prepare(self, target: Path, original: bytes, output: bytes, row: dict, log: Path):
        if self.state.get("pending"):
            raise SafeSkip("recover the pending export before preparing another stamp")
        self.state["pending"] = {
            "target": str(target.resolve()),
            "before": digest(original),
            "after": digest(output),
            "row": row,
            "log": str(log.resolve()),
            "next": self.next + 1,
        }
        self.save()

    def audit_lock(self, log: Path):
        key = str(log.resolve())
        if key not in self.audit_locks:
            log.parent.mkdir(parents=True, exist_ok=True)
            self.audit_locks[key] = FileLock(key + ".lock", timeout=1)
        return self.audit_locks[key]

    @contextmanager
    def guard_id(self, log: Path, part_id: str):
        # Hold through replacement AND audit commit. Separate counters sharing a
        # local log must not both pass the same unused-ID check concurrently.
        lock = self.audit_lock(log)
        try:
            lock.acquire()
        except Timeout as exc:
            raise SafeSkip("another export is using the audit log; try again") from exc
        try:
            if any(row["id"] == part_id for row in read_log(log)):
                raise SafeSkip(
                    f"ID {part_id} already exists in the audit log; restore the counter backup "
                    "or set Next ID above the highest used number"
                )
            yield
        finally:
            lock.release()

    def finish(self):
        pending = self.state["pending"]
        log = Path(pending["log"])
        log.parent.mkdir(parents=True, exist_ok=True)
        # Separate lock permits different local counters to share a CSV safely on
        # one machine. Network filesystems are intentionally not supported yet.
        with self.audit_lock(log):
            rows = read_log(log)
            matching = [r for r in rows if r["transaction"] == pending["row"]["transaction"]]
            if matching and matching != [{k: str(v) for k, v in pending["row"].items()}]:
                raise SafeSkip(
                    "audit transaction conflicts with the pending journal; restore its backup"
                )
            if not matching:
                if any(r["id"] == pending["row"]["id"] for r in rows):
                    raise SafeSkip(
                        "pending ID conflicts with the audit log; preserve the journal for review"
                    )
                stream = io.StringIO(newline="")
                writer = csv.DictWriter(stream, fieldnames=LOG_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
                writer.writerow(pending["row"])
                atomic_write(log, stream.getvalue().encode("utf-8"))
        self.state = {"next": pending["next"], "pending": None}
        self.save()

    def reset(self, value: int):
        if value < self.next:
            raise SafeSkip("counter cannot move backwards; use a new prefix and counter file")
        self.state["next"] = value
        self.save()
