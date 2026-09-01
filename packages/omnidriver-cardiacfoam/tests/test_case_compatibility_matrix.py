"""Existing-case discovery/runnability, for cardiacFoam's own markers.

Moved from omnidriver/tests/core/test_case_compatibility_matrix.py (Phase 2
Task M2): these three parametrized rows -- a bare electroProperties file, an
electroProperties.variant file, and the full dict-set row -- exercise
cardiacFoam's own has_case_marker/is_runnable_without_workflow (an
electroProperties file marks a folder as a cardiacFoam case), not core's
generic entrypoint-based discovery. The two rows that test only core's own
mechanism (an empty folder, and a bare Allrun) stayed in core, run under
generic_openfoam_context().
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.registry import list_entries
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(
    CardiacFoamPlugin(), source="test:case_compatibility_matrix",
)


def _touch(case_root: Path, relative: str) -> None:
    path = case_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


@pytest.mark.parametrize(
    ("files", "discovered", "runnable"),
    [
        (("constant/electroProperties",), True, False),
        (("constant/electroProperties.variant",), True, False),
        (
            (
                "constant/electroProperties",
                "constant/physicsProperties",
                "system/controlDict",
                "system/fvSchemes",
                "system/fvSolution",
            ),
            True,
            True,
        ),
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
