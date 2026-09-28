"""OpenFOAM case-script, generated-root, and decomposition conventions."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.reconciler import declared_instance_names
from omnidriver.core.runtime.registry import list_entries
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
from omnidriver.openfoam.environment import openfoam_environment_context


def _touch(case_root: Path, relative: str) -> None:
    path = case_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_openfoam_declares_allrun_case_scripts() -> None:
    manifest = openfoam_environment_context().capabilities.manifest.manifest()
    assert manifest["allowed_commands"]["case_scripts"] == sorted(
        openfoam_case_runtime_conventions().case_script_commands
    )


@pytest.mark.parametrize("generated_directory", ("postProcessing", "logs"))
def test_openfoam_hides_declared_generated_roots(tmp_path: Path, generated_directory: str) -> None:
    case_root = tmp_path / generated_directory / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")
    assert list_entries(tmp_path, driver_context=openfoam_environment_context()) == []


def test_openfoam_hides_parallel_decomposition_output(tmp_path: Path) -> None:
    assert openfoam_case_runtime_conventions().replica_directory_globs == ("processor*",)
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")
    assert list_entries(tmp_path, driver_context=openfoam_environment_context()) == []


def test_openfoam_time_directories_are_its_instances(tmp_path: Path) -> None:
    """"0" is a preserved instance, not just a numeric one."""
    for name in ("0", "0.001", "1e-05", "constant", "processor0", "postProcessing"):
        (tmp_path / name).mkdir()
    assert declared_instance_names(tmp_path, driver_context=openfoam_environment_context()) == ("0", "0.001", "1e-05")
    assert openfoam_case_runtime_conventions().preserved_instance_names == ("0",)
