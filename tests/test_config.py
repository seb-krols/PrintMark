from __future__ import annotations

import json
from dataclasses import replace

import pytest

from basemark.config import Settings, load_settings, notes_overrides, save_settings
from basemark.env import diagnostic_env, job_from
from basemark.errors import SafeSkip


def test_all_four_layers(tmp_path):
    path = tmp_path / "config.toml"
    save_settings(path, Settings(text_height_mm=7, layers=1, counter_prefix="A"))
    settings = load_settings(path, "Regular notes\nbasemark: size=8; layers=2", {"layers": 3})
    assert settings.text_height_mm == 8
    assert settings.layers == 3
    assert settings.counter_prefix == "A"
    assert settings.margin_mm == 2  # built-in


def test_escaped_notes_and_paths(tmp_path):
    assert notes_overrides(r"comment\nbasemark: layers=2; size=6; label=PETG") == {
        "layers": 2,
        "text_height_mm": 6.0,
        "label": "PETG",
    }
    assert (
        Settings(counter_file="data/counter.json").paths(tmp_path)[0]
        == tmp_path / "data/counter.json"
    )


def test_slicer_quoted_filament_notes():
    notes = json.dumps("PETG profile\nbasemark: layers=3; size=7")
    assert notes_overrides(notes) == {"layers": 3, "text_height_mm": 7.0}


@pytest.mark.parametrize(
    "data",
    [
        {"layers": 4},
        {"layers": True},
        {"mode": "silent"},
        {"text_height_mm": float("nan")},
        {"margin_mm": -1},
        {"counter_next": 0},
        {"counter_prefix": "bad; code"},
        {"material_map": []},
        {"template": "{material.__class__} {id}"},
        {"template": "{material} {id!r}"},
        {"template": "{material}"},
        {"template": "{material} {id:2}"},
        {"enabled": "false"},
        {"template": "{"},
        {"template": "{{material}} {id}"},
        {"template": "{material} {{id}}"},
    ],
)
def test_invalid_config_rejected(data):
    with pytest.raises(SafeSkip):
        replace(Settings(), **data).validate()


def test_unknown_keys_not_silently_ignored(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("layerz = 2\n")
    with pytest.raises(SafeSkip, match="unknown"):
        load_settings(path)
    with pytest.raises(SafeSkip, match="unknown"):
        notes_overrides("basemark: counter_file=evil.json")


def test_env_wins_over_embedded_settings(gcode):
    job = job_from(
        {"SLIC3R_FILAMENT_TYPE": "PET", "SLIC3R_PP_OUTPUT_NAME": "final.gcode"},
        gcode,
        Settings(material_map={"PET": "PETG"}),
        "temp.gcode",
    )
    assert job.material == "PETG"
    assert job.output_name == "final.gcode"


@pytest.mark.parametrize(
    "key,value",
    [
        ("FILAMENT_TYPE", "PLA;PETG"),
        ("SPIRAL_VASE", "1"),
        ("COMPLETE_OBJECTS", "1"),
        ("GCODE_FLAVOR", "makerware"),
        ("BINARY_GCODE", "1"),
        ("NOZZLE_DIAMETER", "nan"),
    ],
)
def test_unsupported_profiles(gcode, key, value):
    with pytest.raises(SafeSkip):
        job_from({"SLIC3R_" + key: value}, gcode, Settings(), "temp.gcode")


def test_dump_default_omits_credentials():
    env = {"SLIC3R_FILAMENT_TYPE": "PLA", "SLIC3R_PRINTHOST_APIKEY": "secret", "TOKEN": "secret"}
    assert json.loads(diagnostic_env(env)) == {"SLIC3R_FILAMENT_TYPE": "PLA"}
    assert "SLIC3R_PRINTHOST_APIKEY" in json.loads(diagnostic_env(env, all_keys=True))
    assert "TOKEN" not in json.loads(diagnostic_env(env, all_keys=True))


def test_windows_utf8_bom_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('counter_prefix = "A"\n', encoding="utf-8-sig")
    assert load_settings(path).counter_prefix == "A"
