"""physics_layout.json covers every native case, and every region it
resolves exists (spec 2026-09-26 A7, owner amendment). Supplied only
through OMNIDRIVER_NATIVE_TUTORIALS, never discovered.

Widened 2026-09-26 (R1 fix, finding I1): the original test only globbed
``constant/physicsProperties``, so a native case that has no such file
(``electrophysiologyProtocols/ionicHeterogeneity``, which runs
``ionicHeterogeneityProbe`` and reads ``constant/electroProperties``
directly) was never examined here, even though it lost its mesh-scale
exemption when the hook's swallow was widened to catch every exception.
``test_a_case_without_physics_properties_is_single_region`` and
``test_the_hook_still_exempts_a_case_without_physics_properties`` close
that gap.
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
    """Every native case with ``constant/electroProperties`` and no
    ``constant/physicsProperties`` -- the layout ``_IMPLICIT_LAYOUT`` covers
    (finding I1's fix direction 3: "widen the drift gate so it also finds
    native cases with an electroProperties and no physicsProperties")."""
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
    """The pre-A7 hook, verbatim: it read ``constant/electroProperties``
    directly, with no region split at all."""
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
    """Finding I1's fix direction 4: the hook's answer for a case with no
    ``physicsProperties`` (``ionicHeterogeneity``, among others) must match
    what the pre-A7 direct read of ``constant/electroProperties`` gave --
    it must not have silently regressed to "not exempt"."""
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
