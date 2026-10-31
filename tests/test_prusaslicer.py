import sys

import pytest

from basemark import prusaslicer
from basemark.__main__ import main
from basemark.config import Settings
from basemark.prusaslicer import (
    SetupError,
    check,
    join_strings,
    read_ini,
    script_lines,
    setup,
    split_strings,
    with_hook,
)

VENDOR = """[vendor]
name = Prusa Research

[print:*common*]
layer_height = 0.2
bottom_solid_layers = 4
arc_fitting = emit_center
post_process =

[print:*structural*]
perimeters = 3

[print:0.15mm STRUCTURAL @MK4IS 0.4]
inherits = *common*; *structural*
layer_height = 0.15
alias = 0.15mm STRUCTURAL
compatible_printers_condition = printer_notes=~/.*MK4IS.*/

[printer:*mk4*]
binary_gcode = 1
nozzle_diameter = 0.4
printer_notes = PRINTER_MODEL_MK4IS

[printer:Original Prusa MK4 Input Shaper 0.4 nozzle]
inherits = *mk4*
printer_model = MK4IS
"""


@pytest.fixture
def data(tmp_path, monkeypatch):
    root = tmp_path / "PrusaSlicer"
    for kind in ("vendor", "print", "printer", "filament"):
        (root / kind).mkdir(parents=True)
    (root / "vendor/PrusaResearch.ini").write_text(VENDOR, encoding="utf-8")
    (root / "PrusaSlicer.ini").write_text(
        "view_mode = expert\n\n[presets]\nfilament = Generic PLA @PGIS\n"
        "print = 0.15mm STRUCTURAL @MK4IS 0.4\n"
        "printer = Original Prusa MK4 Input Shaper 0.4 nozzle\n\n[recent]\nx = 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(prusaslicer, "bundle_files", lambda d: sorted((d / "vendor").glob("*")))
    monkeypatch.setattr(prusaslicer, "prusaslicer_running", lambda: False)
    monkeypatch.setattr(prusaslicer, "data_dir", lambda: root)
    return root


COMMAND = f'"{sys.executable}" -m basemark'  # what hook_command() gives a source install


def test_string_lists_round_trip():
    items = ['"C:\\Program Files\\BaseMark\\basemark.exe" --mode auto', "plain;semi", ""]
    assert split_strings(join_strings(items)) == items
    assert split_strings("") == []
    assert split_strings("script.py;other.py") == ["script.py", "other.py"]
    assert script_lines('"a\\nb";c') == ["a", "b", "c"]


def test_hook_replaces_old_basemark_and_keeps_other_scripts():
    old = join_strings(['"C:\\old\\basemark.exe"\nC:\\tools\\rename.py'])
    assert script_lines(with_hook(old, COMMAND)) == ["C:\\tools\\rename.py", COMMAND]


def test_setup_from_system_presets(data):
    done = setup(COMMAND)
    assert len(done) == 3
    print_ini = read_ini(data / "print/0.15mm STRUCTURAL @MK4IS 0.4 + BaseMark.ini")[""]
    # Fully resolved from the vendor chain: PrusaSlicer fills gaps from defaults, not parents.
    assert print_ini["layer_height"] == "0.15"
    assert print_ini["perimeters"] == "3" and print_ini["bottom_solid_layers"] == "4"
    assert print_ini["inherits"] == "0.15mm STRUCTURAL @MK4IS 0.4"
    assert print_ini["arc_fitting"] == "disabled"
    assert script_lines(print_ini["post_process"]) == [COMMAND]
    assert "alias" not in print_ini
    assert print_ini["compatible_printers_condition"] == "printer_notes=~/.*MK4IS.*/"
    printer_ini = read_ini(
        data / "printer/Original Prusa MK4 Input Shaper 0.4 nozzle + BaseMark.ini"
    )
    assert printer_ini[""]["binary_gcode"] == "0"
    assert printer_ini[""]["inherits"] == "Original Prusa MK4 Input Shaper 0.4 nozzle"
    assert printer_ini[""]["printer_model"] == "MK4IS"
    app = read_ini(data / "PrusaSlicer.ini")
    assert app["presets"]["print"] == "0.15mm STRUCTURAL @MK4IS 0.4 + BaseMark"
    assert app["presets"]["printer"] == "Original Prusa MK4 Input Shaper 0.4 nozzle + BaseMark"
    assert app["presets"]["filament"] == "Generic PLA @PGIS" and app["recent"]["x"] == "1"
    assert (data / "PrusaSlicer.ini.basemark-backup").is_file()
    findings = check(Settings(counter_prefix="A"), COMMAND)
    assert all(f.ok is not False for f in findings)


def test_setup_keeps_user_preset_parent_and_reruns_in_place(data):
    (data / "print/My PLA.ini").write_text(
        "inherits = 0.15mm STRUCTURAL @MK4IS 0.4\nlayer_height = 0.1\narc_fitting = disabled\n"
        'post_process = "C:\\\\tools\\\\rename.py"\n',
        encoding="utf-8",
    )
    (data / "printer/Mine + Basemark.ini").write_text(
        "inherits = Original Prusa MK4 Input Shaper 0.4 nozzle\nbinary_gcode = 0\n",
        encoding="utf-8",
    )
    text = (data / "PrusaSlicer.ini").read_text(encoding="utf-8")
    text = text.replace("print = 0.15mm STRUCTURAL @MK4IS 0.4", "print = My PLA")
    text = text.replace(
        "printer = Original Prusa MK4 Input Shaper 0.4 nozzle", "printer = Mine + Basemark"
    )
    (data / "PrusaSlicer.ini").write_text(text, encoding="utf-8")
    setup(COMMAND)
    created = read_ini(data / "print/My PLA + BaseMark.ini")[""]
    assert created["inherits"] == "0.15mm STRUCTURAL @MK4IS 0.4"
    assert created["layer_height"] == "0.1"
    assert script_lines(created["post_process"]) == ["C:\\tools\\rename.py", COMMAND]
    # The printer already exported plain G-code, so no copy is made and it stays selected.
    assert not (data / "printer/Mine + Basemark + BaseMark.ini").exists()
    assert read_ini(data / "PrusaSlicer.ini")["presets"]["printer"] == "Mine + Basemark"
    setup(COMMAND)  # selected preset is now the BaseMark copy: update it in place
    assert not (data / "print/My PLA + BaseMark + BaseMark.ini").exists()
    assert read_ini(data / "PrusaSlicer.ini")["presets"]["print"] == "My PLA + BaseMark"


def test_check_lists_what_to_fix(data):
    findings = check(Settings(), COMMAND)
    problems = " ".join(f.text for f in findings if f.ok is False)
    assert "no BaseMark post-processing script" in problems
    assert "arc fitting is on" in problems and "binary G-code" in problems
    assert not any("prefix" in f.text for f in findings)


def test_missing_hook_program_and_thin_bottoms_are_reported(data):
    (data / "print/Thin.ini").write_text(
        "inherits = 0.15mm STRUCTURAL @MK4IS 0.4\nbottom_solid_layers = 2\n"
        'post_process = "\\"C:\\\\gone\\\\basemark.exe\\""\n',
        encoding="utf-8",
    )
    text = (data / "PrusaSlicer.ini").read_text(encoding="utf-8")
    text = text.replace("print = 0.15mm STRUCTURAL @MK4IS 0.4", "print = Thin")
    (data / "PrusaSlicer.ini").write_text(text, encoding="utf-8")
    texts = [f.text for f in check(Settings(layers=2), COMMAND)]
    assert any("missing program" in t for t in texts)
    assert any("2 solid bottom layers" in t for t in texts)


def test_setup_refuses_while_prusaslicer_runs(data, monkeypatch):
    monkeypatch.setattr(prusaslicer, "prusaslicer_running", lambda: True)
    with pytest.raises(SetupError, match="Close PrusaSlicer"):
        setup(COMMAND)
    assert not list((data / "print").iterdir())


def test_cli_check_and_setup(data, tmp_path, capsys):
    config = tmp_path / "config.toml"
    assert main(["--config", str(config), "--check-prusaslicer"]) == 2
    assert "Not ready yet" in capsys.readouterr().out
    assert main(["--config", str(config), "--setup-prusaslicer"]) == 0
    output = capsys.readouterr().out
    assert "BaseMark hook added" in output and "Ready" in output


MK4 = "Original Prusa MK4 Input Shaper 0.4 nozzle"


def network_printer(data, name, presets, *, legacy=False):
    """A physical printer as PrusaSlicer 2.7 saves it (OctoPrint on the lab network)."""
    folder = data / "physical_printer"
    folder.mkdir(exist_ok=True)
    names = "" if legacy else f"preset_names = {join_strings(presets)}\n"
    path = folder / f"{name}.ini"
    path.write_text(
        "# generated by PrusaSlicer 2.7.4+win64\nhost_type = octoprint\n"
        f"preset_name = {presets[0]}\n{names}print_host = 192.168.1.50\n"
        "printhost_apikey = SECRET\nprinter_technology = FFF\n",
        encoding="utf-8",
    )
    return path


def choose_network_printer(data, name):
    ini = data / "PrusaSlicer.ini"
    text = ini.read_text(encoding="utf-8")
    ini.write_text(text.replace("[presets]\n", f"[presets]\nphysical_printer = {name}\n"))


def test_setup_lets_network_printers_use_the_basemark_printer_preset(data):
    lab = network_printer(data, "Lab OctoPi", [MK4])
    mini = network_printer(data, "MINI OctoPi", ["Original Prusa MINI"])
    old = network_printer(data, "Old OctoPi", [MK4], legacy=True)
    choose_network_printer(data, "Lab OctoPi")
    done = setup(COMMAND)
    assert "Physical printer “Lab OctoPi” (OctoPrint): can use it." in done
    assert "Send to printer “Lab OctoPi” (OctoPrint) runs BaseMark too." in done
    for path in (lab, old):
        values = read_ini(path)[""]
        assert split_strings(values["preset_names"]) == [MK4, f"{MK4} + BaseMark"]
        assert values["printhost_apikey"] == "SECRET" and values["preset_name"] == MK4
        assert path.with_name(path.name + ".basemark-backup").is_file()
    assert split_strings(read_ini(mini)[""]["preset_names"]) == ["Original Prusa MINI"]
    app = read_ini(data / "PrusaSlicer.ini")["presets"]
    assert app["physical_printer"] == "Lab OctoPi" and app["printer"] == f"{MK4} + BaseMark"
    findings = check(Settings(), COMMAND)
    assert all(f.ok is not False for f in findings)
    assert any(
        "“Lab OctoPi” (OctoPrint): Send to printer runs BaseMark" in f.text for f in findings
    )
    assert not any("SECRET" in f.text for f in findings)
    setup(COMMAND)  # again: nothing added twice
    assert split_strings(read_ini(lab)[""]["preset_names"]) == [MK4, f"{MK4} + BaseMark"]


def test_check_flags_a_network_printer_that_would_switch_presets(data):
    network_printer(data, "Lab OctoPi", ["Some Other Printer"])
    choose_network_printer(data, "Lab OctoPi")
    findings = check(Settings(), COMMAND)
    assert any(
        f.ok is False and "doesn't list printer preset" in f.text and "Some Other" in f.text
        for f in findings
    )
