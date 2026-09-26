"""OpenFOAM-owned provenance interpretations exercised through Core mechanics."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
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
    """Final review M5: before this fix, ``latestTime`` picked a candidate
    time directory by ``float(name)`` succeeding, a rule that disagreed with
    ``instance_directory_pattern`` (the same rule staging/discovery use) on
    names like ``inf``. A directory literally named ``inf`` parses as a
    float but is not an instance by the conventions regex, so it must be
    ignored here too -- the rule is stated once, not twice with different
    answers."""
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


def test_a_missing_control_dict_still_answers_the_zero_default(tmp_path: Path) -> None:
    """Final review M5: a stricter refusal here was attempted and reverted
    the same day (see `time_selection.selected_start_time`'s docstring) --
    it broke `omnidriver-cardiaccore`'s
    `test_controlled_allrun_executes_without_domain_claims`, a real,
    pre-existing case that is deliberately not OpenFOAM-shaped at all. This
    characterization test pins the restored behaviour: a missing
    controlDict still answers the silent default ``"0"``, unchanged from
    before this review."""
    from omnidriver.openfoam.mutators import read_foam_entry

    assert selected_start_time(
        tmp_path,
        control_dict_relpath="system/controlDict",
        read_value=read_foam_entry,
        instance_directory_pattern=openfoam_case_runtime_conventions().instance_directory_pattern,
    ) == "0"


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
    assert OpenFOAMEnvironmentPlugin().get_input_roots(
        tmp_path, {}, conventions=openfoam_case_runtime_conventions(),
    ) == ("0.5", "processor0/0.5", "processor1/0.5")


class _CollatedLayoutPlugin:
    """A minimal companion provider stacked on top of
    ``OpenFOAMEnvironmentPlugin`` that overrides only the replica
    convention (a collated ``procs*`` layout instead of ``processor*``).
    Implements exactly the required ``SolverPlugin`` contract -- nothing
    solver-shaped beyond that -- so it can join a provider stack without
    colliding with OpenFOAM's own case-file declarations or its exclusive
    hooks (``apply_overrides``, ...)."""

    plugin_name = "collated layout test plugin"
    plugin_id = "test.collated-layout"
    plugin_version = "1.0.0"
    plugin_api_version = "2"

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

    def get_tutorial_catalog(self):
        return {"registered_tutorials": (), "spec_factories": {}}

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
    """R2 fix, finding I2: the OpenFOAM layer must read the STACK's merged
    replica convention, not always its own default. A stacked provider that
    redeclares ``replica_directory_globs`` (here, a collated ``procs*``
    layout instead of ``processor*``) makes provenance follow it too, not
    just staging/discovery -- both go through
    ``case_runtime_conventions.conventions()``, and ``get_case_runtime_conventions``
    composes ``single`` (most specific wins), so the companion's answer, not
    OpenFOAM's, is what every core mechanic reads."""
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
