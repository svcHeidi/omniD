"""Canonical input enumeration (Task 2b): which on-disk files, case
scripts, and runtime dependencies a workflow run actually consumes.
Classification is by consumption, not authorship (I1) -- an
unclassified file defaults to required_input, since a spurious refusal
is recoverable and a silent stale replay is the incident this phase
exists to prevent.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from omnidriver.core.plugin_capabilities import (
    CaseRuntimeConventions,
    ResolvedInput,
    RuntimeDependency,
)
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
from omnidriver.core.runtime.attempt_lease import acquire_attempt_lease, acquire_case_lease
from omnidriver.core.runtime.remediation_transaction import (
    begin_remediation_transaction,
    finish_remediation_transaction,
    mark_remediation_dispatching,
    record_remediation_outcome,
)
from plugins.minimal_plugin import MinimalTestPlugin


def _paths(components, *, kind: str | None = None) -> set[str]:
    return {c.path for c in components if kind is None or c.kind == kind}


def _by_path(components, path: str):
    matches = [c for c in components if c.path == path]
    assert len(matches) == 1, f"expected exactly one component for {path!r}, got {matches}"
    return matches[0]


def _record_accepted_transaction(case_root: Path, output_dir: Path, **kwargs):
    effective_resolution = kwargs.pop("effective_resolution", ())
    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            transaction = begin_remediation_transaction(
                case_root, output_dir=output_dir, **kwargs,
            )
            validated = finish_remediation_transaction(
                case_root, transaction, status="validated",
                effective_resolution=effective_resolution,
            )
            dispatching = mark_remediation_dispatching(case_root, validated)
            return record_remediation_outcome(
                case_root, dispatching, execution_status="ok", attempt=1,
            )


def _write_control_dict(case_root: Path, *, start_from: str, start_time: str = "0") -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "controlDict").write_text(
        f"startFrom       {start_from};\nstartTime       {start_time};\n"
        "endTime         1;\ndeltaT          0.01;\n"
    )


def _make_executable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class _FakePlugin(MinimalTestPlugin):
    """A v1 plugin that declares CaseProvenanceCapability / RuntimeEvidence
    hooks inline, so precedence can be exercised without a tutorial.

    Its selected-time convention is supplied below, because Core does not
    infer a restart directory from case-file syntax."""

    def __init__(self, *, required_inputs=(), generated_output_globs=(), extra_provenance_paths=()):
        self._required_inputs = required_inputs
        self._generated_output_globs = generated_output_globs
        self._extra_provenance_paths = extra_provenance_paths

    def get_required_inputs(self, case_root, resolved_case):
        return self._required_inputs

    def get_generated_output_globs(self, case_root, resolved_case):
        return self._generated_output_globs

    def get_extra_provenance_paths(self, case_root):
        return self._extra_provenance_paths

    def get_input_roots(self, case_root, resolved_case, *, conventions):
        """The toy's state directory "0", serially and in each processor*
        replica: the shape an OpenFOAM stack declares, stated by hand."""
        del resolved_case, conventions
        replicas = sorted(p.name for p in Path(case_root).glob("processor*") if p.is_dir())
        return ("0", *(f"{name}/0" for name in replicas))

    def get_profile(self) -> PluginProfile:
        rules = (
            CaseFileRule(
                path="system/controlDict", kind="test_configuration",
                role="x-test.configuration", required="always",
            ),
            CaseFileRule(
                path="constant", kind="test_input_directory",
                role="x-test.input_directory", required="always",
            ),
        )
        return PluginProfile(
            path=Path(__file__), plugin_id=self.plugin_id,
            api_version=self.plugin_api_version, case_files=rules, cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                "case_profile": {"dictionaries": [{
                    "path": rule.path, "kind": rule.kind, "role": rule.role,
                    "required": rule.required,
                } for rule in rules]},
            },
        )

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(
            replica_directory_globs=("processor*",),
            case_entrypoints=("run-case",),
            case_script_commands=("run-case",),
        )


def test_selected_start_time_directory_is_included_others_excluded(tmp_path: Path) -> None:
    """Corrected 2026-09-26 (R2 fix, finding M3): ``_FakePlugin.get_input_roots``
    always returns ``"0"`` by hand, so the ``startTime``/``startFrom`` keys
    ``_write_control_dict`` writes into ``system/controlDict`` here are never
    read by core -- this proves core walks whatever input root the plugin
    declares, not that core interprets OpenFOAM's start-time keywords (it
    does not; that lives entirely in ``OpenFOAMEnvironmentPlugin.get_input_roots``,
    covered by ``test_provenance_integration.py``'s
    ``test_latest_time_selection_is_an_openfoam_adapter_convention`` and
    ``test_openfoam_declares_its_start_time_and_replicas_as_input_roots``)."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    for time_name in ("0", "0.5", "1"):
        time_dir = tmp_path / time_name
        time_dir.mkdir()
        (time_dir / "Vm").write_text(f"field-at-{time_name}")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(_FakePlugin(), source="test"),
    )
    included = _paths(components, kind="case_file")

    assert "0/Vm" in included
    assert "0.5/Vm" not in included
    assert "1/Vm" not in included


class _ForeignEnvironmentPlugin(MinimalTestPlugin):
    """A plugin that declares its input roots without case-file roles."""

    def __init__(self, *, roots: tuple[str, ...]) -> None:
        self._roots = roots

    def get_profile(self) -> PluginProfile:
        return PluginProfile(
            path=Path(__file__),
            plugin_id=self.plugin_id,
            api_version=self.plugin_api_version,
            case_files=(),
            cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                "case_profile": {"dictionaries": []},
            },
        )

    def get_input_roots(self, case_root, resolved_case, *, conventions):
        del conventions
        return self._roots


def test_a_foreign_plugins_declared_input_roots_are_walked_as_given(
    tmp_path: Path,
) -> None:
    """Corrected 2026-09-26 (R2 fix, finding M3): this was named
    ``..._overrides_the_openfoam_default``, but there is no OpenFOAM default
    in core to override -- ``_ForeignEnvironmentPlugin`` declares no
    ``openfoam.control_dict`` role at all, and no stack here composes more
    than one provider, so nothing is "overridden". What this proves is
    simpler and still real: core walks exactly the input roots a plugin
    declares, whatever they are, with no OpenFOAM-shaped fallback baked in
    when a plugin implements the hook."""
    for time_name in ("0", "0.5", "1"):
        time_dir = tmp_path / time_name
        time_dir.mkdir()
        (time_dir / "Vm").write_text(f"field-at-{time_name}")

    plugin = _ForeignEnvironmentPlugin(roots=("0.5",))
    assert plugin.get_profile().case_files == ()

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(plugin, source="test"),
    )
    included = _paths(components, kind="case_file")

    assert "0.5/Vm" in included
    assert "0/Vm" not in included
    assert "1/Vm" not in included


@pytest.mark.parametrize("bad", ["", ".", "/abs", "../up", 3])
def test_an_input_root_must_be_a_case_relative_path_inside_the_case(tmp_path: Path, bad) -> None:
    """A blank root would walk the whole case tree (``case_root / ""``); an
    absolute or escaping one would walk outside it. The adapter refuses
    each by name instead."""
    plugin = _ForeignEnvironmentPlugin(roots=(bad,))
    with pytest.raises(TypeError, match="get_input_roots"):
        enumerate_case_inputs(
            tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(plugin, source="test"),
        )


def test_a_plugins_own_replica_naming_convention_is_walked_as_declared(
    tmp_path: Path,
) -> None:
    """Corrected 2026-09-26 (R2 fix, finding M3): this was named
    ``..._overrides_processor``, and its docstring said a ``rank0`` layout
    "still gets them walked as I9 inputs ... (Tier 3)" -- Tier 3's bare
    optional hooks (``get_decomposition_dirname_prefix``) are gone since A2;
    the plugin now simply lists ``rank0/0`` by hand via ``get_input_roots``,
    so this proves only that core walks the roots it is given, not that any
    "processor" default is overridden."""
    rank0 = tmp_path / "rank0"
    (rank0 / "0").mkdir(parents=True)
    (rank0 / "0" / "Vm").write_text("decomposed restart field")
    stray_processor0 = tmp_path / "processor0"
    (stray_processor0 / "0").mkdir(parents=True)
    (stray_processor0 / "0" / "Vm").write_text("not this plugin's convention")

    plugin = _ForeignEnvironmentPlugin(roots=("0", "rank0/0"))

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(plugin, source="test"),
    )
    included = _paths(components, kind="case_file")

    assert "rank0/0/Vm" in included
    assert "processor0/0/Vm" not in included


def test_postprocessing_and_workflow_logs_are_excluded(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "postProcessing" / "workflow_logs").mkdir(parents=True)
    (tmp_path / "postProcessing" / "workflow_logs" / "solve.attempt1.stdout.log").write_text("log")
    (tmp_path / "postProcessing" / "ecgProbes" / "0").mkdir(parents=True)
    (tmp_path / "postProcessing" / "ecgProbes" / "0" / "data").write_text("probe data")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(_FakePlugin(), source="test"),
    )
    included = _paths(components, kind="case_file")

    assert not any(path.startswith("postProcessing/") for path in included)


def test_a_case_with_no_constant_does_not_raise(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(_FakePlugin(), source="test"),
    )

    assert "system/controlDict" in _paths(components, kind="case_file")


def test_generic_plugin_still_requires_unknown_files(tmp_path: Path) -> None:
    """Under the generic plugin (declares nothing), the same file cardiacFoam
    would exclude stays required -- an unclassified file always defaults to
    required_input (I1)."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "C").write_bytes(b"mesh-diagnostic-byproduct")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(_FakePlugin(), source="test"),
    )

    assert "constant/C" in _paths(components, kind="case_file")


def test_a_declared_case_script_named_by_the_dag_is_included(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    _make_executable(tmp_path / "run-case", b"#!/bin/sh\nrunner\n")

    workflow_dag = {"steps": [{"id": "solve", "command": "run-case", "depends_on": []}]}
    components = enumerate_case_inputs(
        tmp_path, workflow_dag=workflow_dag, driver_context=driver_context(_FakePlugin(), source="test"),
    )

    script = _by_path(components, "run-case")
    assert script.kind == "case_file"
    assert script.strength == "content"


def test_a_parallel_step_includes_both_mpirun_and_its_payload(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    bin_dir = tmp_path / "fakebin"
    _make_executable(bin_dir / "mpirun", b"#!/bin/sh\necho mpirun\n")
    _make_executable(bin_dir / "cardiacFoam", b"#!/bin/sh\necho solve\n")

    workflow_dag = {
        "steps": [
            {
                "id": "solve",
                "command": "mpirun",
                "args": ["-np", "4", "cardiacFoam", "-parallel"],
                "depends_on": [],
            }
        ]
    }
    env = {"PATH": str(bin_dir)}
    components = enumerate_case_inputs(
        tmp_path, workflow_dag=workflow_dag, driver_context=driver_context(_FakePlugin(), source="test"), env=env,
    )

    mpirun = _by_path(components, "mpirun")
    payload = _by_path(components, "cardiacFoam")
    assert mpirun.kind == "runtime_dependency"
    assert mpirun.strength == "content"
    assert payload.kind == "runtime_dependency"
    assert payload.strength == "content"


def test_a_required_but_unresolved_step_executable_is_unavailable_not_omitted(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    workflow_dag = {"steps": [{"id": "mesh", "command": "blockMesh", "depends_on": []}]}
    env = {"PATH": str(tmp_path / "nowhere")}

    components = enumerate_case_inputs(
        tmp_path, workflow_dag=workflow_dag, driver_context=driver_context(_FakePlugin(), source="test"), env=env,
    )

    block_mesh = _by_path(components, "blockMesh")
    assert block_mesh.kind == "runtime_dependency"
    assert block_mesh.strength == "unavailable"


def test_plugin_runtime_dependency_entries_appear_and_missing_required_is_unavailable(
    tmp_path: Path,
) -> None:
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    present_lib = tmp_path / "libbin" / "libBar.dylib"
    present_lib.parent.mkdir(parents=True)
    present_lib.write_bytes(b"library contents")

    plugin = _FakePlugin(
        extra_provenance_paths=(
            RuntimeDependency(name="libFoo", path=None, required=True),
            RuntimeDependency(name="libBar", path=present_lib, required=False),
        )
    )
    context = driver_context(plugin, source="test")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=context,
    )

    lib_foo = _by_path(components, "libFoo")
    lib_bar = _by_path(components, "libBar")
    assert lib_foo.kind == "runtime_dependency"
    assert lib_foo.strength == "unavailable"
    assert lib_bar.strength == "content"


def test_dag_consumes_declaration_wins_over_a_generated_output_glob(tmp_path: Path) -> None:
    """I1's resolution precedence: a DAG step's consumes declaration beats a
    plugin's generated_output_globs exclusion."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "C").write_bytes(b"mesh-diagnostic-byproduct")

    workflow_dag = {
        "steps": [
            {
                "id": "verify",
                "command": "postProcess",
                "depends_on": [],
                "consumes": ["constant/C"],
            }
        ]
    }
    components = enumerate_case_inputs(
        tmp_path, workflow_dag=workflow_dag, driver_context=driver_context(_FakePlugin(), source="test"),
    )

    assert "constant/C" in _paths(components, kind="case_file")


def test_plugin_required_inputs_entry_wins_over_a_generated_output_glob(tmp_path: Path) -> None:
    """I1's resolution precedence: a plugin required_inputs() entry beats its
    own generated_output_globs exclusion."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "constant").mkdir()
    target = tmp_path / "constant" / "C"
    target.write_bytes(b"actually consumed this time")

    plugin = _FakePlugin(
        required_inputs=(ResolvedInput(name="C", path=target, required=True, consumer="test"),),
        generated_output_globs=("constant/C",),
    )
    context = driver_context(plugin, source="test")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=context,
    )

    assert "constant/C" in _paths(components, kind="case_file")


def test_optional_required_input_that_is_absent_is_not_added(tmp_path: Path) -> None:
    """READ_IF_PRESENT and absent is not the same as MUST_READ and missing --
    nothing was going to be consumed, so nothing is fingerprinted."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    plugin = _FakePlugin(
        required_inputs=(ResolvedInput(name="Optional", path=None, required=False, consumer="test"),),
    )
    context = driver_context(plugin, source="test")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=context,
    )

    assert "Optional" not in _paths(components)


def test_accepted_external_effective_dependency_is_fingerprinted(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    _write_control_dict(case_root, start_from="startTime", start_time="0")
    external = tmp_path / "runtime" / "included.cfg"
    external.parent.mkdir()
    external.write_text("value 1;\n")
    _record_accepted_transaction(
        case_root, tmp_path / "output",
        step_id="solve",
        overrides=[{"driver_path": "value", "value": "1"}],
        hypothesis="use the runtime-provided value",
        target_paths=(case_root / "system" / "controlDict",),
        effective_resolution=({"inspected_files": [str(external)]},),
    )
    context = driver_context(_FakePlugin(), source="test")

    before = enumerate_case_inputs(
        case_root, workflow_dag={"steps": []}, driver_context=context,
    )
    external.write_text("value 2;\n")
    after = enumerate_case_inputs(
        case_root, workflow_dag={"steps": []}, driver_context=context,
    )

    dependency_name = f"effective_config:{external.resolve()}"
    assert _by_path(before, dependency_name).digest != _by_path(after, dependency_name).digest


def test_sequential_repairs_conservatively_retain_prior_external_dependencies(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    _write_control_dict(case_root, start_from="startTime", start_time="0")
    external_a = tmp_path / "runtime" / "a.cfg"
    external_b = tmp_path / "runtime" / "b.cfg"
    external_a.parent.mkdir()
    external_a.write_text("a 1;\n")
    external_b.write_text("b 2;\n")
    output_dir = tmp_path / "output"
    first = _record_accepted_transaction(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "a", "value": "1"}],
        hypothesis="first repair",
        target_paths=(case_root / "system" / "controlDict",),
        effective_resolution=({"inspected_files": [str(external_a)]},),
    )
    second = _record_accepted_transaction(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "b", "value": "2"}],
        hypothesis="second repair",
        target_paths=(case_root / "system" / "controlDict",),
        effective_resolution=({"inspected_files": [str(external_b)]},),
    )

    components = enumerate_case_inputs(
        case_root,
        workflow_dag={"steps": []},
        driver_context=driver_context(_FakePlugin(), source="test"),
    )

    assert f"effective_config:{external_a.resolve()}" in _paths(
        components, kind="runtime_dependency",
    )
    assert f"effective_config:{external_b.resolve()}" in _paths(
        components, kind="runtime_dependency",
    )


def test_processor_selected_time_is_included_other_processor_times_excluded(tmp_path: Path) -> None:
    """I9: processor*/<selected-time>/** is a required input on the same
    footing as the serial case; other times under processor*/ are outputs."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    proc0 = tmp_path / "processor0"
    (proc0 / "0").mkdir(parents=True)
    (proc0 / "0" / "Vm").write_text("decomposed restart field")
    (proc0 / "0.5").mkdir(parents=True)
    (proc0 / "0.5" / "Vm").write_text("later time, not an input")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(_FakePlugin(), source="test"),
    )
    included = _paths(components, kind="case_file")

    assert "processor0/0/Vm" in included
    assert "processor0/0.5/Vm" not in included
