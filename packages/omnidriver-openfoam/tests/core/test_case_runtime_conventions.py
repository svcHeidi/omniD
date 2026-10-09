"""OpenFOAM case-script and time-directory conventions."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.capability_manifest import capability_manifest
from omnidriver.core.runtime.reconciler import declared_instance_names
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
from omnidriver.core.plugin_interface import load_plugin_context


def test_openfoam_declares_allrun_case_scripts() -> None:
    manifest = capability_manifest(load_plugin_context("openfoam-environment"))
    assert manifest["allowed_commands"]["case_scripts"] == sorted(
        openfoam_case_runtime_conventions().case_script_commands
    )


def test_openfoam_time_directories_are_its_instances(tmp_path: Path) -> None:
    """"0" is a preserved instance, not just a numeric one."""
    for name in ("0", "0.001", "1e-05", "constant", "processor0", "postProcessing"):
        (tmp_path / name).mkdir()
    assert declared_instance_names(tmp_path, driver_context=load_plugin_context("openfoam-environment")) == ("0", "0.001", "1e-05")
    assert openfoam_case_runtime_conventions().preserved_instance_names == ("0",)


def test_staging_keeps_a_supplied_mesh_and_drops_run_output(tmp_path: Path) -> None:
    """Only run output is dropped by name; a mesh is dropped only where a record's step declares it produced."""
    from omnidriver.core.runtime.sweep_runner import _stage_entry_case

    source = tmp_path / "case"
    for relpath in (
        "constant/polyMesh/points", "slab.msh", "slab.geo", "0/Vm",
        "0.01/Vm", "processor0/0/Vm", "postProcessing/probes/0/Vm", "log.cardiacFoam",
    ):
        (source / relpath).parent.mkdir(parents=True, exist_ok=True)
        (source / relpath).write_text(relpath)
    staged = tmp_path / "staged"
    _stage_entry_case(source, staged, driver_context=load_plugin_context("openfoam-environment"))

    kept = {path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()}
    assert kept == {"constant/polyMesh/points", "slab.msh", "slab.geo", "0/Vm"}
