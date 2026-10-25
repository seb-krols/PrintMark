from __future__ import annotations

from pathlib import Path

import pytest

from basemark import notify
from basemark.__main__ import main
from basemark.service import Outcome


def test_stamped_export_shows_a_notice(job_file, tmp_path, notices):
    assert main(["--config", str(tmp_path / "config.toml"), "--mode", "auto", str(job_file)]) == 0
    assert notices == ["stamped"]


def test_safe_skip_is_announced(tmp_path, notices):
    job = tmp_path / "job.gcode"
    job.write_text("G1 X0 Y0\n", encoding="utf-8")
    assert main(["--config", str(tmp_path / "config.toml"), "--mode", "auto", str(job)]) == 0
    assert notices == ["skipped"]


def test_notice_can_be_turned_off(job_file, tmp_path, notices):
    config = tmp_path / "config.toml"
    config.write_text("notify = false\n", encoding="utf-8")
    assert main(["--config", str(config), "--mode", "auto", str(job_file)]) == 0
    assert notices == []


def test_check_and_dry_run_stay_quiet(job_file, tmp_path, notices):
    main(["--config", str(tmp_path / "config.toml"), "--check", str(job_file)])
    main(["--config", str(tmp_path / "config.toml"), "--dry-run", str(job_file)])
    assert notices == []


def test_operator_skip_and_disabled_are_not_repeated():
    assert not notify.wanted(Outcome("skipped", notify.USER_SKIP))
    assert not notify.wanted(Outcome("disabled", "BaseMark is off; file unchanged."))
    assert notify.wanted(Outcome("skipped", "G2 is unsupported"))
    assert notify.wanted(Outcome("error", "ValueError: x"))


def test_notice_texts():
    tone, title, body = notify.texts("stamped", "Stamped >PLA< A001 · 2 layers · 6 mm · 159 moves.")
    assert (tone, title, body) == ("ok", "Stamped >PLA< A001", "2 layers · 6 mm · 159 moves")
    tone, title, body = notify.texts("skipped", "G2 is unsupported; disable arcs")
    assert tone == "warn" and title == "Export not stamped"
    assert body.startswith("G2 is unsupported") and "unchanged" in body


def test_notice_command_is_windowed_and_detached_from_pipes(tmp_path):
    args = notify.command(tmp_path / "config.toml", "stamped", "msg", "job.gcode")
    assert args[-6:] == [
        "--notify",
        "stamped",
        "msg",
        "job.gcode",
        "--config",
        str(tmp_path / "config.toml"),
    ]
    assert "basemark.notify" in args


def test_notice_window_renders(tmp_path):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    try:
        notify.show("skipped", "G2 is unsupported", "C:/Jobs/part.gcode", Path("c.toml"), root=root)
        root.update()
        assert root.winfo_width() > 100 and root.winfo_height() > 40
    finally:
        root.destroy()
