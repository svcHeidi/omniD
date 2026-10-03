"""OpenFOAM-owned provenance interpretations exercised through Core mechanics."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_interface import CaseRuntimeConventions
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
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
        instance_directory_pattern=openfoam_case_runtime_conventions().instance_directory_pattern,
    ) == "0.5"


def test_latest_time_selection_uses_the_conventions_regex_not_float(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, "startFrom latestTime;\nstartTime 0;\n")
    for name in ("0", "0.5", "inf", "nan", "1_0", "+1"):
        (tmp_path / name).mkdir()

    from omnidriver.openfoam.mutators import read_foam_entry

    assert selected_start_time(
        tmp_path,
        control_dict_relpath="system/controlDict",
        read_value=read_foam_entry,
        instance_directory_pattern=openfoam_case_runtime_conventions().instance_directory_pattern,
    ) == "0.5"


def test_a_missing_control_dict_contributes_no_roots_at_all(tmp_path: Path) -> None:
    """A missing controlDict means the case may not be OpenFOAM-shaped at
    all, so it is neither refused nor defaulted to "0"."""
    from omnidriver.openfoam.mutators import read_foam_entry

    assert selected_start_time(
        tmp_path,
        control_dict_relpath="system/controlDict",
        read_value=read_foam_entry,
        instance_directory_pattern=openfoam_case_runtime_conventions().instance_directory_pattern,
    ) is None
    assert OpenFOAMEnvironmentPlugin().get_input_roots(
        tmp_path, {}, conventions=openfoam_case_runtime_conventions(),
    ) == ()


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
    assert OpenFOAMEnvironmentPlugin().get_input_roots(
        tmp_path, {}, conventions=openfoam_case_runtime_conventions(),
    ) == ("0.5", "processor0/0.5", "processor1/0.5")


class _CollatedLayoutPlugin:
    """Minimal companion plugin overriding only the replica convention
    (collated ``procs*`` instead of ``processor*``)."""

    plugin_name = "collated layout test plugin"
    plugin_id = "test.collated-layout"
    plugin_version = "1.0.0"
    plugin_api_version = "3"

    def get_profile(self):
        from omnidriver.core.plugin_profile import PluginProfile

        return PluginProfile(
            path=Path(__file__), plugin_id=self.plugin_id, api_version=self.plugin_api_version,
            case_files=(), cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                "case_profile": {"dictionaries": []},
            },
        )

    def get_capabilities(self):
        return {}

    def validate_configuration(self, spec):
        return ()

    def validate_run_semantics(self, context):
        return ()

    def predict_data_artifacts(self, case_root, spec):
        return ()

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        from dataclasses import replace

        return replace(
            openfoam_case_runtime_conventions(),
            replica_directory_globs=("procs*",),
        )


def test_a_stacked_providers_merged_replica_globs_are_what_provenance_walks(tmp_path: Path) -> None:
    """A stacked provider's own `replica_directory_globs` is what provenance
    walks, not OpenFOAM's default -- `get_case_runtime_conventions` composes
    "most specific wins"."""
    _write_control_dict(tmp_path, "startFrom startTime;\nstartTime 0;\n")
    for relpath in ("0/Vm", "procs4/0/Vm", "processor0/0/Vm"):
        _write(tmp_path, relpath)

    components = enumerate_case_inputs(
        tmp_path,
        workflow_dag={"steps": []},
        driver_context=driver_context(
            OpenFOAMEnvironmentPlugin(), _CollatedLayoutPlugin(), source="test",
        ),
    )
    included = {c.path for c in components if c.kind == "case_file"}

    assert "procs4/0/Vm" in included
    assert "processor0/0/Vm" not in included
