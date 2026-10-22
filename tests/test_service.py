from __future__ import annotations

import csv
import json
from dataclasses import replace

import pytest
from conftest import coupon

from basemark.__main__ import main
from basemark.config import Settings, save_settings
from basemark.counter import Counter
from basemark.errors import SafeSkip
from basemark.service import process


def test_full_export_id_log_and_duplicate_protection(job_file, tmp_path):
    result = process(
        job_file,
        tmp_path / "config.toml",
        {"mode": "auto", "counter_prefix": "A"},
        {"SLIC3R_PP_OUTPUT_NAME": "final-output.gcode"},
    )
    assert result.status == "stamped"
    assert result.part_id == "A001"
    assert json.loads((tmp_path / "counter.json").read_text())["next"] == 2
    rows = list(csv.DictReader((tmp_path / "log.csv").open()))
    assert rows[0]["id"] == "A001"
    assert rows[0]["gcode_filename"] == "final-output.gcode"
    assert "coupon.stl" in rows[0]["object_names"]
    stamped = job_file.read_bytes()
    with pytest.raises(SafeSkip, match="already"):
        process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert job_file.read_bytes() == stamped


def test_dry_run_preview_does_not_consume_id(job_file, tmp_path):
    original = job_file.read_bytes()
    svg = tmp_path / "preview.svg"
    result = process(job_file, tmp_path / "config.toml", {}, {}, dry_run=True, preview=svg)
    assert result.status == "preview"
    assert "seen from below" in svg.read_text()
    assert job_file.read_bytes() == original
    assert not (tmp_path / "counter.json").exists()
    assert not (tmp_path / "log.csv").exists()


def test_cancel_and_invalid_drag_preserve_input(job_file, tmp_path):
    original = job_file.read_bytes()
    result = process(job_file, tmp_path / "config.toml", {}, {}, choose=lambda *args: None)
    assert result.status == "skipped"
    assert job_file.read_bytes() == original
    assert not (tmp_path / "counter.json").exists()
    with pytest.raises(SafeSkip, match="outside"):
        process(
            job_file,
            tmp_path / "config.toml",
            {},
            {},
            choose=lambda f, s, p, *args: replace(p, x=9999),
        )
    assert job_file.read_bytes() == original


def test_failure_before_replace_keeps_source_and_counter(job_file, tmp_path, monkeypatch):
    import basemark.service as service

    original = job_file.read_bytes()
    monkeypatch.setattr(
        service, "atomic_write", lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
    )
    with pytest.raises(OSError):
        process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert job_file.read_bytes() == original
    assert json.loads((tmp_path / "counter.json").read_text())["next"] == 1


def test_audit_failure_is_reported_as_stamped_not_unchanged(job_file, tmp_path, monkeypatch):
    original_finish = Counter.finish
    monkeypatch.setattr(Counter, "finish", lambda _: (_ for _ in ()).throw(OSError("log locked")))
    result = process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.status == "stamped-pending-audit"
    assert job_file.read_text().startswith("; BASEMARK stamp")
    monkeypatch.setattr(Counter, "finish", original_finish)
    with Counter(tmp_path / "counter.json") as counter:
        assert counter.next == 2


def test_failure_after_replace_retains_recoverable_journal(job_file, tmp_path, monkeypatch):
    import basemark.service as service

    real_write = service.atomic_write

    def replace_then_fail(path, data, **kwargs):
        real_write(path, data, **kwargs)
        raise OSError("directory fsync failure")

    monkeypatch.setattr(service, "atomic_write", replace_then_fail)
    result = process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.status == "stamped-pending-audit"
    assert job_file.read_text().startswith("; BASEMARK stamp")
    with Counter(tmp_path / "counter.json") as recovered:
        assert recovered.next == 2


def test_standalone_serialized_filament_notes(job_file, tmp_path):
    job_file.write_text(job_file.read_text() + '; filament_notes = "basemark: enabled=false"\n')
    result = process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.status == "disabled"


@pytest.mark.parametrize("bad", [b"GCDEbinary", b"PK\x03\x04zip", b"G1 X1\0oops", b"\xff"])
def test_binary_or_invalid_encoding_is_nonfatal(job_file, tmp_path, bad, capsys):
    job_file.write_bytes(bad)
    assert main(["--config", str(tmp_path / "config.toml"), "--mode", "auto", str(job_file)]) == 0
    assert job_file.read_bytes() == bad
    assert "skipped" in capsys.readouterr().err


def test_too_small_nonfatal(job_file, tmp_path, capsys):
    job_file.write_text(coupon(width=5, depth=5))
    original = job_file.read_bytes()
    assert main(["--config", str(tmp_path / "config.toml"), "--mode", "auto", str(job_file)]) == 0
    assert job_file.read_bytes() == original
    assert "skipped" in capsys.readouterr().err
    assert not (tmp_path / "counter.json").exists()


def test_off_bypasses_invalid_config(job_file, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("invalid!!!!!")
    original = job_file.read_bytes()
    assert main(["--config", str(config), "--off", str(job_file)]) == 0
    assert job_file.read_bytes() == original


def test_notes_disable_and_cli_enable(job_file, tmp_path):
    config = tmp_path / "config.toml"
    save_settings(config, Settings(mode="auto"))
    env = {"SLIC3R_FILAMENT_NOTES": "basemark: enabled=false"}
    assert process(job_file, config, {}, env).status == "disabled"
    assert process(job_file, config, {"enabled": True}, env).status == "stamped"


def test_path_collisions_never_overwrite_source(job_file, tmp_path):
    original = job_file.read_bytes()
    with pytest.raises(SafeSkip, match="different paths"):
        process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {}, preview=job_file)
    with pytest.raises(SafeSkip, match="different paths"):
        process(job_file, tmp_path / "config.toml", {"counter_file": str(job_file)}, {})
    assert job_file.read_bytes() == original


def test_hardlinked_lock_cannot_truncate_gcode(job_file, tmp_path):
    import os

    original = job_file.read_bytes()
    try:
        os.link(job_file, tmp_path / "counter.json.lock")
    except OSError:
        pytest.skip("hard links are not available on this filesystem")
    with pytest.raises(SafeSkip, match="different paths"):
        process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert job_file.read_bytes() == original
