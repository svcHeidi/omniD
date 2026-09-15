"""OpenFOAM case-script, generated-root, and decomposition conventions."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.registry import list_entries
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin, openfoam_environment_context


def _touch(case_root: Path, relative: str) -> None:
    path = case_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_openfoam_declares_allrun_case_scripts() -> None:
    manifest = OpenFOAMEnvironmentPlugin().get_capabilities()
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
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")
    assert list_entries(tmp_path, driver_context=openfoam_environment_context()) == []
