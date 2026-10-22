from __future__ import annotations

import csv
import json

import pytest

from basemark.config import atomic_write
from basemark.counter import LOG_FIELDS, Counter
from basemark.errors import SafeSkip


def row():
    return dict.fromkeys(LOG_FIELDS, "") | {"transaction": "unique", "id": "A001"}


def test_counter_only_advances_after_replacement(tmp_path):
    path, target, log = tmp_path / "counter.json", tmp_path / "job.gcode", tmp_path / "log.csv"
    target.write_bytes(b"original")
    with Counter(path) as counter:
        counter.prepare(target, b"original", b"stamped", row(), log)
        assert counter.next == 1
        atomic_write(target, b"stamped")
        counter.finish()
        assert counter.next == 2
    assert len(list(csv.DictReader(log.open()))) == 1


@pytest.mark.parametrize("replaced", [False, True])
def test_crash_recovery_at_commit_boundary(tmp_path, replaced):
    path, target, log = tmp_path / "counter.json", tmp_path / "job.gcode", tmp_path / "log.csv"
    target.write_bytes(b"original")
    with Counter(path) as counter:
        counter.prepare(target, b"original", b"stamped", row(), log)
        if replaced:
            atomic_write(target, b"stamped")
        # Simulate process death: context releases lock, no finish.
    with Counter(path) as recovered:
        assert recovered.next == (2 if replaced else 1)
        assert recovered.state["pending"] is None
    assert log.exists() == replaced


def test_missing_interrupted_target_blocks_id_reuse(tmp_path):
    path, target, log = tmp_path / "counter.json", tmp_path / "job.gcode", tmp_path / "log.csv"
    with Counter(path) as counter:
        counter.prepare(target, b"before", b"after", row(), log)
    with pytest.raises(SafeSkip, match="missing"):
        with Counter(path):
            pass
    assert json.loads(path.read_text())["next"] == 1


def test_csv_recovery_idempotent(tmp_path, monkeypatch):
    path, target, log = tmp_path / "counter.json", tmp_path / "job.gcode", tmp_path / "log.csv"
    target.write_bytes(b"before")
    with Counter(path) as counter:
        counter.prepare(target, b"before", b"after", row(), log)
        target.write_bytes(b"after")
        monkeypatch.setattr(counter, "save", lambda: (_ for _ in ()).throw(OSError("crash")))
        with pytest.raises(OSError):
            counter.finish()
    with Counter(path) as counter:
        assert counter.next == 2
    assert len(list(csv.DictReader(log.open()))) == 1


def test_concurrent_lock_and_monotonic_floor(tmp_path):
    path = tmp_path / "counter.json"
    with Counter(path, minimum=40) as counter:
        with pytest.raises(SafeSkip, match="another export"):
            with Counter(path):
                pass
        counter.reset(42)
    with Counter(path, minimum=1) as counter:
        assert counter.next == 42
        with pytest.raises(SafeSkip, match="backwards"):
            counter.reset(1)
