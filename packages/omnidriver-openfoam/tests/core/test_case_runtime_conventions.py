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
    # Corrected 2026-09-22 (final whole-branch review, bundled Minor):
    # `OpenFOAMEnvironmentPlugin.get_capabilities()` now returns `{}`,
    # matching `CardiacCorePlugin.get_capabilities()` (Task 10's rule --
    # a provider builds no manifest of its own when core can compose one).
    # The composed manifest capability is the real assertion now, same
    # correction `test_plugin_capabilities.py` made for Task 10 itself.
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
    """OpenFOAM declares its numeric time directories as instances, and
    "0" as preserved (spec 2026-09-26 A2): byte-for-byte the old rule."""
    for name in ("0", "0.001", "1e-05", "constant", "processor0", "postProcessing"):
        (tmp_path / name).mkdir()
    assert declared_instance_names(tmp_path, driver_context=openfoam_environment_context()) == ("0", "0.001", "1e-05")
    assert openfoam_case_runtime_conventions().preserved_instance_names == ("0",)
