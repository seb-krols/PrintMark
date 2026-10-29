"""Real Tk interaction smoke tests; skipped on machines without a display."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from basemark.config import NUMBERED, Settings, load_settings, save_settings
from basemark.service import demo_data


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def single(material="PETG"):
    """The demo plate's bracket on its own: the one-part export window."""
    plate, placements, settings = demo_data(material)
    return replace(plate, parts=plate.parts[:1]), placements[:1], settings


def test_placement_drag_resize_rotate_invalid_accept_and_skip(root):
    from basemark.popup import PlacementWindow

    plate, placements, settings = single()
    placed, surface = placements[0], plate.parts[0].surface
    app = PlacementWindow(root, plate, placements, settings, "PETG", "A042", demo=True)
    root.update()
    assert app.status.cget("text").startswith("✓")
    assert app.ok.winfo_viewable()
    assert app.ok.winfo_rooty() + app.ok.winfo_height() <= root.winfo_rooty() + root.winfo_height()
    x, y = app.screen(placed.x, placed.y)
    app.start_drag(SimpleNamespace(x=x, y=y))
    app.drag(SimpleNamespace(x=x + 20, y=y))
    assert app.placed.x < placed.x  # underside view mirrors X
    app.resize(-0.5)
    assert app.placed.height == placed.height - 0.5
    for _ in range(10):
        app.resize(-0.5)
    assert app.placed.height == 2.0  # by hand down to the hard limit
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


def test_minimized_placement_window_is_restored(root):
    from basemark.popup import PlacementWindow

    app = PlacementWindow(root, *single(), "PETG", "A042")
    root.update()
    root.iconify()
    root.update()
    app.keep_visible()
    root.update()
    assert root.state() != "iconic"
    app.skip()


def test_placement_accept(root):
    from basemark.popup import PlacementWindow

    plate, placements, settings = single()
    app = PlacementWindow(root, plate, placements, settings, "PETG", "A042")
    root.update()
    assert app.ok.cget("text") == "Apply stamp"
    app.accept()
    assert app.result == placements


def test_plate_select_leave_out_and_zoom(root):
    from basemark.popup import PlacementWindow

    plate, placements, settings = demo_data()
    assert all(placements)  # the demo tag is big enough for a 3 mm label
    app = PlacementWindow(root, plate, placements, settings, "PETG", "")
    root.update()
    assert app.ok.cget("text") == "Stamp 2 parts"
    assert app.part_count.cget("text") == "PART 1 OF 2"
    # Clicking the tag's label selects it and drags only that label.
    tag = placements[1]
    x, y = app.screen(tag.x, tag.y)
    app.start_drag(SimpleNamespace(x=x, y=y))
    assert app.index == 1
    app.drag(SimpleNamespace(x=x, y=y + 1))
    assert app.placements[0] == placements[0]
    app.toggle_zoom()
    root.update()
    assert app.zoom_button.cget("text") == "Show the whole plate"
    app.included.set(False)
    app.toggle_part()
    assert app.placements[1] is None
    assert app.ok.cget("text") == "Stamp 1 part"
    app.included.set(True)
    app.toggle_part()
    assert app.placements[1] is not None
    app.step(1)
    assert app.index == 0
    app.placements[1] = replace(app.placements[1], x=999)
    app.draw()
    app.refresh_side()
    assert str(app.ok.cget("state")) == "disabled"  # every label must fit before Apply
    app.placements[1] = None
    app.refresh_side()
    app.accept()
    assert app.result == [placements[0], None]


def test_plate_part_without_room_can_be_switched_on(root):
    from basemark.popup import PlacementWindow

    plate, placements, settings = demo_data()
    app = PlacementWindow(root, plate, [placements[0], None], settings, "PETG", "")
    root.update()
    app.select(1)
    assert app.status.cget("text").endswith("Too small for a label")
    app.included.set(True)
    app.toggle_part()
    assert app.placements[1] is not None


def test_settings_save_and_hook(root, tmp_path):
    from basemark.settings_ui import SettingsWindow

    path = tmp_path / "config.toml"
    app = SettingsWindow(root, path)
    root.update()
    assert str(app.save_button.cget("state")) == "disabled"
    app.values["mode"].set("auto")
    assert not load_settings(path).mode == "auto"  # nothing is written before Save
    assert str(app.save_button.cget("state")) != "disabled"
    assert app.feedback.cget("text").startswith("Unsaved")
    app.save()
    assert load_settings(path).mode == "auto"
    assert str(app.save_button.cget("state")) == "disabled"
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
    process(job_file, config, {"mode": "auto", "template": NUMBERED, "counter_prefix": "A"}, {})
    before = (tmp_path / "counter.json").read_bytes()
    app = SettingsWindow(root, config)
    app.lookup_value.set("A001")
    app.find_part()
    assert "A001 · PLA" in app.lookup_summary
    assert str(job_file) in app.lookup_summary
    app.lookup_value.set("A999")
    app.find_part()
    assert "No matching ID" in app.lookup_summary
    assert (tmp_path / "counter.json").read_bytes() == before


def test_open_window_follows_exports_and_keeps_saving(root, tmp_path, job_file):
    from basemark.service import process
    from basemark.settings_ui import SettingsWindow

    config = tmp_path / "config.toml"
    save_settings(config, Settings(template=NUMBERED))
    app = SettingsWindow(root, config)
    root.update()
    assert app.next_id.cget("text").startswith("Next number 001")
    assert process(job_file, config, {"mode": "auto"}, {}).status == "stamped"
    app.watch_exports()
    assert app.values["counter_next"].get() == "2"
    assert app.next_id.cget("text").startswith("Next number 002")
    assert not app.dirty()  # following the counter is not an unsaved change
    app.values["layers"].set("3")
    app.save()
    assert app.feedback.cget("text").startswith("Saved")
    assert load_settings(config).layers == 3


def test_part_number_switch_edits_the_label(root, tmp_path):
    from basemark.settings_ui import SettingsWindow

    config = tmp_path / "config.toml"
    app = SettingsWindow(root, config)
    root.update()
    assert app.preview.cget("text") == "PLA" and not app.numbered.get()
    app.numbered.set(True)
    app.toggle_numbered()
    assert app.values["template"].get() == NUMBERED
    assert app.preview.cget("text") == "PLA 001"
    app.values["template"].set("{material}")  # typing the label updates the switch
    assert not app.numbered.get()
    app.values["template"].set("{material} {date} {id}")
    app.numbered.set(False)
    app.toggle_numbered()
    assert app.values["template"].get() == "{material} {date}"
    app.discard()
    assert app.values["template"].get() == "{material}" and not app.dirty()


def test_closing_with_unsaved_changes_asks_first(root, tmp_path, monkeypatch):
    from basemark.settings_ui import SettingsWindow, messagebox

    config = tmp_path / "config.toml"
    app = SettingsWindow(root, config)
    root.update()
    app.values["layers"].set("3")
    answers = iter([None, True])
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *a, **k: next(answers))
    app.close()  # Cancel: stays open, nothing saved
    assert root.winfo_exists() and not config.exists()
    app.values["text_height_mm"].set("1")  # invalid: Save fails, window stays open
    app.close()
    assert root.winfo_exists() and not config.exists()
    assert app.feedback.cget("text").startswith("Not saved")
    app.values["text_height_mm"].set("3")
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *a, **k: True)
    app.close()
    assert load_settings(config).layers == 3
