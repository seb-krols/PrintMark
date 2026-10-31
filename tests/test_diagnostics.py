"""Checks and recovery must not turn inspection into a print/counter mutation."""

import json

import pytest

from basemark.__main__ import main
from basemark.config import NUMBERED
from basemark.counter import LOG_FIELDS, Counter
from basemark.diagnostics import read_report
from basemark.errors import SafeSkip
from basemark.service import process


def pending(tmp_path, final=None):
    path = tmp_path / "counter.json"
    row = dict.fromkeys(LOG_FIELDS, "") | {
        "transaction": "crash-test",
        "id": "001",
        "gcode_filename": str(final or "unknown.gcode"),
    }
    with Counter(path) as counter:
        counter.prepare(
            tmp_path / "deleted-temp.gcode", b"before", b"after", row, tmp_path / "log.csv"
        )
    return path


def test_recover_surviving_final_export_automatically(tmp_path):
    final = tmp_path / "final.gcode"
    final.write_bytes(b"after")
    state = pending(tmp_path, final)
    with Counter(state) as counter:
        assert counter.next == 2
        assert counter.state["pending"] is None
    assert final.read_bytes() == b"after"


def test_manual_recovery_requires_exact_hash_and_is_idempotent(tmp_path):
    state = pending(tmp_path)
    final = tmp_path / "final.gcode"
    final.write_bytes(b"different")
    original = state.read_bytes()
    with Counter(state, recover=False) as counter:
        with pytest.raises(SafeSkip, match="does not match"):
            counter.recover_from(final)
    assert state.read_bytes() == original
    final.write_bytes(b"after")
    args = ["--config", str(tmp_path / "config.toml"), "--recover-from", str(final)]
    assert main(args) == 0
    assert final.read_bytes() == b"after"
    assert json.loads(state.read_text())["next"] == 2
    log = (tmp_path / "log.csv").read_bytes()
    assert main(args) == 1
    assert (tmp_path / "log.csv").read_bytes() == log


def test_check_never_recovers_pending_transaction(job_file, tmp_path):
    final = tmp_path / "final.gcode"
    final.write_bytes(b"after")
    state = pending(tmp_path, final)
    original, journal = job_file.read_bytes(), state.read_bytes()
    args = ["--config", str(tmp_path / "config.toml"), "--template", NUMBERED]
    assert main([*args, "--check", str(job_file)]) == 2
    assert job_file.read_bytes() == original
    assert state.read_bytes() == journal
    assert not (tmp_path / "log.csv").exists()


def test_check_success_and_failure_exit_codes_without_mutation(job_file, tmp_path):
    args = ["--config", str(tmp_path / "config.toml"), "--check", str(job_file)]
    original = job_file.read_bytes()
    assert main(args) == 0
    assert job_file.read_bytes() == original
    assert not (tmp_path / "counter.json").exists()
    assert not (tmp_path / "last-export.json").exists()
    job_file.write_bytes(b"GCDEbinary")
    assert main(args) == 2
    assert job_file.read_bytes() == b"GCDEbinary"


def test_last_export_report_success_and_skip(job_file, tmp_path):
    config = tmp_path / "config.toml"
    args = ["--config", str(config), "--mode", "auto", str(job_file)]
    assert "No export" in read_report(config)
    assert main(args) == 0
    report = json.loads((tmp_path / "last-export.json").read_text())
    assert report["status"] == "stamped"
    assert report["part_id"] == ""  # material only by default: no number used
    assert not (tmp_path / "counter.json").exists()
    assert "Stamped" in read_report(config)
    stamped = job_file.read_bytes()
    assert main(args) == 0
    report = json.loads((tmp_path / "last-export.json").read_text())
    assert report["status"] == "skipped"
    assert job_file.read_bytes() == stamped


@pytest.mark.parametrize(
    "name", ["counter.json.lock", "log.csv.lock", "last-export.json", "last-export.json.lock"]
)
def test_protected_paths_cannot_be_input_or_preview(job_file, tmp_path, name):
    protected = tmp_path / name
    protected.write_bytes(job_file.read_bytes())
    original = protected.read_bytes()
    with pytest.raises(SafeSkip, match="different paths"):
        process(protected, tmp_path / "config.toml", {"mode": "auto", "template": NUMBERED}, {})
    with pytest.raises(SafeSkip, match="different paths"):
        process(job_file, tmp_path / "config.toml", {}, {}, dry_run=True, preview=protected)
    assert protected.read_bytes() == original


def test_environment_dump_cannot_overwrite_counter(job_file, tmp_path):
    counter = tmp_path / "counter.json"
    counter.write_bytes(b'{"next": 10, "pending": null}')
    original = counter.read_bytes()
    assert (
        main(
            [
                "--config",
                str(tmp_path / "config.toml"),
                "--dump-env",
                "--diagnostics-output",
                str(counter),
                str(job_file),
            ]
        )
        == 0
    )
    assert counter.read_bytes() == original


def test_send_to_printer_copy_is_stamped_and_named(gcode, tmp_path, monkeypatch):
    # PrusaSlicer's Send to printer: a copy without extension in %TEMP%, host and target name
    # in the environment (BackgroundSlicingProcess::prepare_upload).
    upload = tmp_path / ".PrusaSlicer.upload.1a2b-3c4d-5e6f-7a8b"
    upload.write_text(gcode, encoding="utf-8")
    monkeypatch.setenv("SLIC3R_PP_HOST", "OctoPrint")
    monkeypatch.setenv("SLIC3R_PP_OUTPUT_NAME", "bracket_0.2mm_PLA_MK3S.gcode")
    shown = []
    monkeypatch.setattr("basemark.notify.spawn", lambda *args: shown.append(args))
    config = tmp_path / "config.toml"
    assert main(["--config", str(config), "--mode", "auto", str(upload)]) == 0
    assert upload.read_text(encoding="utf-8").startswith("; BASEMARK stamp")
    report = json.loads((tmp_path / "last-export.json").read_text())
    assert report["status"] == "stamped" and report["host"] == "OctoPrint"
    assert report["source"] == "bracket_0.2mm_PLA_MK3S.gcode"
    assert shown[0][1] == "stamped"
    assert shown[0][3] == "bracket_0.2mm_PLA_MK3S.gcode (sent to OctoPrint)"
