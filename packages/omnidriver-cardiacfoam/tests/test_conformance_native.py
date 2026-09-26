"""cardiacFOAM passes the conformance suite, every check in ``CHECKS``,
against the real cardiacFoam binary and the native tutorials tree
(conformance Task 14; tutorials-are-pointers plan §5f). Every migrated
record joins ``_TARGETS``; leaving a check out would be a waiver.

``SKIP_ENV_DIAGNOSTICS`` (set suite-wide by this package's conftest, and by
core's and OpenFOAM's) turns OpenFOAM's preflight off. C9 is that preflight,
so this module removes the variable for its own tests, as
``omnidriver-openfoam``'s ``test_environment_preflight.py`` does.
"""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiacfoam_native import (
    manufactured_bidomain_conformance_target,
    niederer2011_conformance_target,
    manufactured_eikonal_ecg_conformance_target,
    restitution_curves_conformance_target,
)

pytestmark = pytest.mark.native

_TARGETS = {
    "restitutionCurves": restitution_curves_conformance_target,
    "manufacturedBidomain": manufactured_bidomain_conformance_target,
    "niederer2011": niederer2011_conformance_target,
    "manufacturedEikonalECG": manufactured_eikonal_ecg_conformance_target,
}


@pytest.fixture(autouse=True)
def _real_preflight(monkeypatch):
    monkeypatch.delenv("SKIP_ENV_DIAGNOSTICS", raising=False)


@pytest.mark.parametrize("record", sorted(_TARGETS))
@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_record_passes(record, check_id, tmp_path):
    verdict = run_check(check_id, _TARGETS[record](tmp_path))
    assert verdict.passed, verdict.detail
