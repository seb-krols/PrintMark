"""Real Tk interaction smoke tests; skipped on machines without a display."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from basemark.config import load_settings
from basemark.service import demo_data


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_placement_drag_resize_rotate_invalid_accept_and_skip(root):
    from basemark.popup import PlacementWindow

    footprint, surface, placed, settings = demo_data()
    app = PlacementWindow(root, footprint, surface, placed, settings, "PETG", "A042", demo=True)
    root.update()
    assert app.status.cget("text").startswith("✓")
    assert app.ok.winfo_viewable()
    assert app.ok.winfo_rooty() + app.ok.winfo_height() <= root.winfo_rooty() + root.winfo_height()
    x, y = app.screen(placed.x, placed.y)
    app.start_drag(SimpleNamespace(x=x, y=y))
    app.drag(SimpleNamespace(x=x + 20, y=y))
    assert app.placed.x < placed.x  # underside view mirrors X
    app.resize(-0.5)
    assert app.placed.height == 5.5
    app.rotate()
    assert app.placed.angle == 90
    app.placed = replace(app.placed, x=999)
    app.draw()
    assert str(app.ok.cget("state")) == "disabled"
    app.accept()
    assert app.result is None
    assert root.winfo_exists()
    app.auto()
    assert app.placed.fits(surface)
    app.skip()
    assert app.result is None


def test_placement_accept(root):
    from basemark.popup import PlacementWindow

    footprint, surface, placed, settings = demo_data()
    app = PlacementWindow(root, footprint, surface, placed, settings, "PETG", "A042")
    root.update()
    app.accept()
    assert app.result == placed


def test_settings_save_and_hook(root, tmp_path):
    from basemark.settings_ui import SettingsWindow

    path = tmp_path / "config.toml"
    app = SettingsWindow(root, path)
    root.update()
    app.values["counter_prefix"].set("B")
    app.values["mode"].set("auto")
    app.save()
    assert load_settings(path).counter_prefix == "B"
    assert load_settings(path).mode == "auto"
    assert str(path) in app.hook.get()
    assert app.feedback.cget("text").startswith("Saved")


def test_desktop_launcher_copies_console_hook(root, tmp_path, monkeypatch):
    import sys

    from basemark.settings_ui import SettingsWindow

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "basemark-desktop.exe"))
    app = SettingsWindow(root, tmp_path / "config.toml")
    assert app.hook.get().startswith(f'"{tmp_path / "basemark.exe"}"')


def test_settings_opens_with_missing_pending_target(root, tmp_path):
    from basemark.counter import LOG_FIELDS, Counter
    from basemark.settings_ui import SettingsWindow

    path = tmp_path / "counter.json"
    with Counter(path) as counter:
        counter.prepare(
            tmp_path / "gone.gcode",
            b"before",
            b"after",
            dict.fromkeys(LOG_FIELDS, ""),
            tmp_path / "log.csv",
        )
    before = path.read_bytes()
    app = SettingsWindow(root, tmp_path / "config.toml")
    assert app.values["counter_next"].get() == "1"
    assert path.read_bytes() == before


def test_find_part_displays_export_without_consuming_id(root, tmp_path, job_file):
    from basemark.service import process
    from basemark.settings_ui import SettingsWindow

    config = tmp_path / "config.toml"
    process(job_file, config, {"mode": "auto", "counter_prefix": "A"}, {})
    before = (tmp_path / "counter.json").read_bytes()
    app = SettingsWindow(root, config)
    app.lookup_value.set("A001")
    app.find_part()
    assert "A001 · PLA" in app.lookup_result.get("1.0", "end")
    assert str(job_file) in app.lookup_result.get("1.0", "end")
    app.lookup_value.set("A999")
    app.find_part()
    assert "No matching ID" in app.lookup_result.get("1.0", "end")
    assert (tmp_path / "counter.json").read_bytes() == before
