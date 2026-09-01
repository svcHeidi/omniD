"""Existing-case discovery/runnability, for markers core itself defines.

Phase 2 Task M2: three of the five parametrized rows in this file, plus
their fixture, asserted cardiacFoam's own has_case_marker/
is_runnable_without_workflow (electroProperties as case marker) and moved to
packages/omnidriver-cardiacfoam/tests/test_case_compatibility_matrix.py. The
two rows kept here -- an empty folder, and a bare Allrun -- exercise only
core's own entrypoint-based discovery/runnability
(_has_entrypoint/_is_case_directory in registry.py), which is meaningful
under the plugin-neutral generic_openfoam_context(): GenericOpenFOAMPlugin
declares no has_case_marker hook at all (always False), so these two rows
are driven purely by Allrun's presence, independent of any plugin
vocabulary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import generic_openfoam_context
from omnidriver.core.runtime.registry import list_entries

_CTX = generic_openfoam_context()


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
