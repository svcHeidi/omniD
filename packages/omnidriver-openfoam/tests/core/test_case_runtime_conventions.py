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
