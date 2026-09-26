"""``CardiacFoamPlugin.get_record_key_catalog`` against real native cases
(conformance Task 14 step 4, decisions 1 and 3). The catalogue must list
what ``record_key_validator`` accepts, and nothing it refuses: the two are
the same three rules (``record_key_validation``'s module docstring).
"""
from __future__ import annotations

import pytest
from foamlib import FoamFile

from cardiacfoam_native import RESTITUTION_CURVES_RELPATH, native_tutorials_root

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.physics_layout import PhysicsLayoutError
from omnidriver.cardiacfoam.record_key_validation import record_key_validator
from omnidriver.core.runtime.record_surface import ANY_KEY

pytestmark = pytest.mark.native


def _catalogue(relpath: str):
    return CardiacFoamPlugin().get_record_key_catalog(native_tutorials_root() / relpath)


def test_the_coeffs_token_is_the_cases_own_solver_scope():
    keys = {(e["document"], e["key"]) for e in _catalogue(RESTITUTION_CURVES_RELPATH)}
    assert not [k for k in keys if "$" in k[1]]
    assert ("constant/electroProperties", "singleCellSolverCoeffs.tissue") in keys
    assert ("constant/electroProperties", "myocardiumSolver") in keys
    assert ("constant/physicsProperties", "type") in keys
    assert not [k for k in keys if k[1].startswith(("monodomainSolverCoeffs.", "bidomainSolverCoeffs."))]


def test_every_system_document_of_the_case_is_listed_open_and_nothing_else_is():
    case_root = native_tutorials_root() / RESTITUTION_CURVES_RELPATH
    open_entries = [e for e in _catalogue(RESTITUTION_CURVES_RELPATH) if e["key"] == ANY_KEY]
    assert sorted(e["document"] for e in open_entries) == sorted(
        p.relative_to(case_root).as_posix() for p in (case_root / "system").rglob("*") if p.is_file()
    )
    assert all(e["validated"] is False and "value_kind" not in e for e in open_entries)


def test_every_listed_key_the_case_holds_is_accepted_by_the_validator_with_its_kind():
    """A drift gate between the two halves of one rule set: each concrete
    catalogued key the native case holds, with the case's own value, is
    accepted by the validator as that entry's ``value_kind``, validated.
    Values are read typed, with foamlib (the stack's config reader answers
    text, which the validator's shape check is not for)."""
    case_root = native_tutorials_root() / RESTITUTION_CURVES_RELPATH
    checked = []
    for entry in _catalogue(RESTITUTION_CURVES_RELPATH):
        if entry["key"] == ANY_KEY or "<" in entry["key"] or "[Int]" in entry["key"]:
            continue
        key_path = tuple(entry["key"].split("."))
        try:
            value = FoamFile(case_root / entry["document"])[key_path]
        except KeyError:
            continue
        assert record_key_validator(entry["document"], key_path, value) == (entry["value_kind"], True), entry
        checked.append(entry["key"])
    assert "singleCellSolverCoeffs.tissue" in checked and "myocardiumSolver" in checked


def test_a_region_split_case_is_refused_by_name():
    """``physics_layout.json`` puts a region-split case's electroProperties
    under ``constant/<region>/``; the validator addresses
    ``constant/electroProperties`` only, so listing keys there would list
    keys it refuses."""
    with pytest.raises(PhysicsLayoutError) as excinfo:
        _catalogue("electromechanicsProtocols/springSupportedSlab")
    assert "constant/electroProperties" in str(excinfo.value)
    assert "springSupportedSlab" in str(excinfo.value)
