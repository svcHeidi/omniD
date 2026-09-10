"""Existing-case discovery/runnability, for markers core itself defines.

Phase 2 Task M2: three of the five parametrized rows in this file, plus
their fixture, asserted cardiacFoam's own has_case_marker/
is_runnable_without_workflow (electroProperties as case marker) and moved to
packages/omnidriver-cardiacfoam/tests/test_case_compatibility_matrix.py. The
two rows kept here -- an empty folder, and a bare Allrun -- exercise only
core's own entrypoint-based discovery/runnability
(_has_entrypoint/_is_case_directory in registry.py), which is meaningful
under the plugin-neutral openfoam_environment_context(): OpenFOAMEnvironmentPlugin
declares no has_case_marker hook at all (always False), so these two rows
are driven purely by Allrun's presence, independent of any plugin
vocabulary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import openfoam_environment_context
from omnidriver.core.runtime.registry import list_entries

from plugins.neutral_environment_plugin import NeutralEnvironmentPlugin

_CTX = openfoam_environment_context()


def _touch(case_root: Path, relative: str) -> None:
    path = case_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


@pytest.mark.parametrize(
    ("files", "discovered", "runnable"),
    [
        ((), False, False),
        (("Allrun",), True, True),
    ],
)
def test_existing_case_discovery_and_runnability_matrix(
    tmp_path: Path,
    files: tuple[str, ...],
    discovered: bool,
    runnable: bool,
) -> None:
    case_root = tmp_path / "candidate"
    case_root.mkdir()
    for relative in files:
        _touch(case_root, relative)

    matches = [
        entry for entry in list_entries(tmp_path, driver_context=_CTX)
        if entry["entry_name"] == "candidate"
    ]
    assert bool(matches) is discovered
    if discovered:
        assert matches[0]["is_runnable"] is runnable


@pytest.mark.parametrize("authored_directory", ("postProcessing", "logs"))
def test_neutral_environment_does_not_hide_authored_directory_names(
    tmp_path: Path,
    authored_directory: str,
) -> None:
    """Only an environment may declare which generated roots discovery skips."""
    case_root = tmp_path / authored_directory / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")
    context = driver_context(
        NeutralEnvironmentPlugin(), source="test:neutral-discovery",
    )

    entries = list_entries(tmp_path, driver_context=context)

    assert [entry["entry_path"] for entry in entries] == [
        f"{authored_directory}/nestedCase",
    ]


@pytest.mark.parametrize("generated_directory", ("postProcessing", "logs"))
def test_openfoam_environment_hides_its_declared_generated_roots(
    tmp_path: Path,
    generated_directory: str,
) -> None:
    case_root = tmp_path / generated_directory / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")

    assert list_entries(tmp_path, driver_context=_CTX) == []


def test_neutral_environment_does_not_assume_a_parallel_output_prefix(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")
    context = driver_context(
        NeutralEnvironmentPlugin(), source="test:neutral-decomposition",
    )

    assert [entry["entry_path"] for entry in list_entries(tmp_path, driver_context=context)] == [
        "processor0/nestedCase",
    ]


def test_openfoam_environment_hides_its_parallel_output_prefix(tmp_path: Path) -> None:
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "Allrun")

    assert list_entries(tmp_path, driver_context=_CTX) == []


def test_legacy_resolve_case_models_neutral_shape_has_no_cardiac_keys() -> None:
    from omnidriver.core.compatibility import legacy_resolve_case_models

    class NotCardiac:
        plugin_id = "org.example.notcardiac"

    result = legacy_resolve_case_models(NotCardiac(), case_root=None)
    assert result == {}


def test_legacy_samplable_fields_neutral_shape_has_no_cardiac_keys() -> None:
    from omnidriver.core.compatibility import legacy_samplable_fields

    class NotCardiac:
        plugin_id = "org.example.notcardiac"

    result = legacy_samplable_fields(NotCardiac(), resolved={})
    assert result == {}
