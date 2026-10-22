from __future__ import annotations

import csv
import io
import json

import pytest

from basemark.__main__ import main
from basemark.audit import LOG_FIELDS, format_records, lookup_id, read_log
from basemark.counter import Counter
from basemark.errors import SafeSkip
from basemark.service import process


def record(part_id="A001", transaction="one"):
    return dict.fromkeys(LOG_FIELDS, "") | {
        "transaction": transaction,
        "id": part_id,
        "material": "PETG",
        "gcode_filename": "C:/Lab/épreuve, coupon.gcode",
        "object_names": "a\nb",
    }


def write_log(path, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=LOG_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding="utf-8-sig", newline="")


def test_lookup_exact_id_preserves_unicode_and_multiline_csv(tmp_path):
    log = tmp_path / "log.csv"
    row = record()
    write_log(log, [row, record("B001", "two")])
    before = log.read_bytes()
    assert lookup_id(log, " A001 ") == [row]
    assert not lookup_id(log, "A1")
    assert not lookup_id(log, "a001")
    assert row["gcode_filename"] in format_records([row])
    assert log.read_bytes() == before


def test_lookup_cli_json_has_no_counter_side_effects(tmp_path, capsys):
    log = tmp_path / "log.csv"
    write_log(log, [record()])
    args = ["--config", str(tmp_path / "config.toml"), "--json", "--lookup"]
    assert main([*args, "A001"]) == 0
    assert json.loads(capsys.readouterr().out) == [record()]
    assert main([*args, "A002"]) == 1
    assert json.loads(capsys.readouterr().out) == []
    assert not (tmp_path / "counter.json").exists()
    assert not list(tmp_path.glob("*.lock"))


def test_missing_history_and_duplicate_history_are_explicit(tmp_path):
    assert not read_log(tmp_path / "missing.csv")
    assert "No matching" in format_records([])
    assert "Multiple records" in format_records([record(), record(transaction="two")])


@pytest.mark.parametrize(
    "content",
    [
        "",
        "id,material\n001,PLA\n",
        ",".join(LOG_FIELDS) + "\none,A001\n",
        ",".join(LOG_FIELDS) + '\n"unterminated',
    ],
)
def test_bad_log_prevents_gcode_mutation(job_file, tmp_path, content):
    log = tmp_path / "log.csv"
    log.write_text(content, encoding="utf-8")
    before, log_before = job_file.read_bytes(), log.read_bytes()
    with pytest.raises(SafeSkip):
        process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert job_file.read_bytes() == before
    assert log.read_bytes() == log_before
    assert not (tmp_path / "counter.json").exists()


def test_lost_counter_cannot_reuse_a_logged_id(job_file, tmp_path):
    config = tmp_path / "config.toml"
    original = job_file.read_bytes()
    process(job_file, config, {"mode": "auto"}, {})
    log_before = (tmp_path / "log.csv").read_bytes()
    (tmp_path / "counter.json").unlink()
    job_file.write_bytes(original)
    with pytest.raises(SafeSkip, match="ID 001 already exists"):
        process(job_file, config, {"mode": "auto"}, {})
    assert job_file.read_bytes() == original
    assert (tmp_path / "log.csv").read_bytes() == log_before
    assert not (tmp_path / "counter.json").exists()
    result = process(job_file, config, {"mode": "auto", "counter_next": 2}, {})
    assert result.part_id == "002"


def test_separate_counters_serialize_unused_id_check_and_commit(tmp_path):
    log = tmp_path / "log.csv"
    target = tmp_path / "job.gcode"
    with Counter(tmp_path / "a.json") as first, Counter(tmp_path / "b.json") as second:
        with first.guard_id(log, "A001"):
            with pytest.raises(SafeSkip, match="using the audit log"):
                with second.guard_id(log, "A001"):
                    pytest.fail("two counters acquired the same log lock")
            first.prepare(target, b"before", b"after", record(), log)
            target.write_bytes(b"after")
            first.finish()  # Must be reentrant on the held log lock.
        with pytest.raises(SafeSkip, match="already exists"):
            with second.guard_id(log, "A001"):
                pytest.fail("duplicate ID escaped the audit check")


def test_conflicting_transaction_retains_journal(tmp_path):
    log = tmp_path / "log.csv"
    target = tmp_path / "job.gcode"
    write_log(log, [record("A099")])
    with Counter(tmp_path / "counter.json") as counter:
        counter.prepare(target, b"before", b"after", record(), log)
        with pytest.raises(SafeSkip, match="conflicts"):
            counter.finish()
        assert counter.state["pending"] is not None
        assert counter.next == 1


def test_lookup_cannot_accidentally_postprocess_a_file(job_file, tmp_path):
    before = job_file.read_bytes()
    with pytest.raises(SystemExit) as exc:
        main(["--lookup", "A001", str(job_file)])
    assert exc.value.code == 2
    assert job_file.read_bytes() == before
