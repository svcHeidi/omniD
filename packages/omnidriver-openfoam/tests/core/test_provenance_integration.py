"""OpenFOAM-owned provenance interpretations exercised through Core mechanics."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.time_selection import selected_start_time


def _components(case_root: Path):
    return enumerate_case_inputs(
        case_root,
        workflow_dag={"steps": []},
        driver_context=driver_context(OpenFOAMEnvironmentPlugin(), source="test"),
    )


def _component(components, path: str):
    matches = [component for component in components if component.path == path]
    assert len(matches) == 1
    return matches[0]


def _write_control_dict(case_root: Path, text: str) -> None:
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "controlDict").write_text(text)


def test_latest_time_selection_is_an_openfoam_adapter_convention(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, "startFrom latestTime;\nstartTime 0;\n")
    for name in ("0", "0.5"):
        (tmp_path / name).mkdir()

    from omnidriver.openfoam.mutators import read_foam_entry

    assert selected_start_time(
        tmp_path,
        control_dict_relpath="system/controlDict",
        read_value=read_foam_entry,
    ) == "0.5"


def test_external_include_changes_openfoam_provenance_identity(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    external = tmp_path / "runtime" / "included.cfg"
    external.parent.mkdir()
    external.write_text("endTime 1;\n")
    _write_control_dict(
        case_root,
        f'#include "{external}"\nstartFrom startTime;\nstartTime 0;\n',
    )

    before = _components(case_root)
    external.write_text("endTime 2;\n")
    after = _components(case_root)

    name = f"effective_config:{external.resolve()}"
    assert _component(before, name).digest != _component(after, name).digest


def test_optional_openfoam_include_records_absence_then_content(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    external = tmp_path / "runtime" / "optional.cfg"
    _write_control_dict(
        case_root,
        f'#includeIfPresent "{external}"\nstartFrom startTime;\nstartTime 0;\n',
    )

    absent = _components(case_root)
    external.parent.mkdir()
    external.write_text("endTime 2;\n")
    present = _components(case_root)

    name = f"effective_config:{external.resolve()}"
    witness = _component(absent, name)
    assert (witness.method, witness.strength, witness.role) == (
        "verified_absence", "absence", "optional_input",
    )
    assert _component(present, name).strength == "content"


def _write(case_root: Path, relpath: str) -> None:
    path = case_root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(relpath)


def test_the_start_time_is_walked_serially_and_in_every_replica(tmp_path: Path) -> None:
    """What an OpenFOAM stack fingerprints from its time and replica
    directories (I9). A characterization: it passes before A2c moves the
    rule out of core, and must pass unchanged after."""
    _write_control_dict(tmp_path, "startFrom startTime;\nstartTime 0;\n")
    for relpath in ("0/Vm", "0.5/Vm", "processor0/0/Vm", "processor0/0.5/Vm", "processor1/0/Vm"):
        _write(tmp_path, relpath)
    included = {c.path for c in _components(tmp_path) if c.kind == "case_file"}
    assert {"0/Vm", "processor0/0/Vm", "processor1/0/Vm"} <= included
    assert not {"0.5/Vm", "processor0/0.5/Vm"} & included


def test_openfoam_declares_its_start_time_and_replicas_as_input_roots(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, "startFrom latestTime;\nstartTime 0;\n")
    for relpath in ("0/Vm", "0.5/Vm", "processor1/0.5/Vm", "processor0/0.5/Vm", "processorX.txt"):
        _write(tmp_path, relpath)
    assert OpenFOAMEnvironmentPlugin().get_input_roots(tmp_path, {}) == ("0.5", "processor0/0.5", "processor1/0.5")
