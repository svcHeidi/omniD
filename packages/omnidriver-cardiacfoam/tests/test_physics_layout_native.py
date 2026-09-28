"""physics_layout.json covers every native case, and every region it resolves
exists, including cases with no ``constant/physicsProperties``. The tree is
supplied only through OMNIDRIVER_NATIVE_TUTORIALS, never discovered.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.detection import (
    detect_myocardium_solver_name,
    detect_verification_model_type,
)
from omnidriver.cardiacfoam.physics_layout import _table, physics_type, region_of
from omnidriver.cardiacfoam.planning_policy import is_nondimensional_case

pytestmark = pytest.mark.native


def _native_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail("OMNIDRIVER_NATIVE_TUTORIALS is not set; a native test needs it supplied")
    return Path(value)


def _cases() -> list[Path]:
    root = _native_root()
    return sorted(
        p.parent.parent for p in root.rglob("constant/physicsProperties")
        if "results" not in p.relative_to(root).parts
    )


def _cases_without_physics_properties() -> list[Path]:
    """Native cases with electroProperties and no physicsProperties (``_IMPLICIT_LAYOUT``)."""
    root = _native_root()
    found = sorted(
        p.parent.parent for p in root.rglob("constant/electroProperties")
        if "results" not in p.relative_to(root).parts
    )
    return [case for case in found if not (case / "constant" / "physicsProperties").exists()]


class _Spec:
    def __init__(self, case_root: Path) -> None:
        self.case_root = case_root


def _pre_a7_answer(electro_properties_path: Path) -> bool:
    """The hook's answer from a direct ``constant/electroProperties`` read, no region split."""
    try:
        return (
            detect_myocardium_solver_name(electro_properties_path) == "singleCellSolver"
            or detect_verification_model_type(electro_properties_path) is not None
        )
    except KeyError:
        return False


def test_every_native_physics_type_has_a_row_and_its_regions_exist():
    cases = _cases()
    assert cases, "no native case found, so this proves nothing"
    split = 0
    for case in cases:
        layout = _table()[physics_type(case)]
        for role in layout.get("regions", {}):
            region = region_of(case, role)
            assert (case / "constant" / region).is_dir(), (case, role, region)
            split += 1
    assert split, "no region-split case found, so the region path is unproved"


def test_a_case_without_physics_properties_is_single_region():
    cases = _cases_without_physics_properties()
    assert cases, "no native case without physicsProperties found, so this proves nothing"
    for case in cases:
        assert region_of(case, "electro") is None, (
            f"{case} has no constant/physicsProperties, but resolved as region-split"
        )


def test_the_hook_still_exempts_a_case_without_physics_properties_the_way_it_used_to():
    """For a case with no physicsProperties the hook matches a direct electroProperties read."""
    cases = _cases_without_physics_properties()
    assert cases, "no native case without physicsProperties found, so this proves nothing"
    mismatched = []
    for case in cases:
        old = _pre_a7_answer(case / "constant" / "electroProperties")
        new = is_nondimensional_case(_Spec(case))
        if new != old:
            mismatched.append((case, old, new))
    assert mismatched == [], (
        f"the hook's answer changed for a case without physicsProperties: {mismatched}"
    )
