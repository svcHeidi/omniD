"""Every cardiacFOAM record in ``_TARGETS`` passes every conformance check against the real binary.
C9 is OpenFOAM's preflight, which the suite-wide ``SKIP_ENV_DIAGNOSTICS`` turns off, so this
module removes that variable for its own tests."""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiacfoam_native import (
    cable_1d_cv_convergence_conformance_target,
    cable_1d_restitution_conformance_target,
    manufactured_bath_bidomain_conformance_target,
    manufactured_bidomain_conformance_target,
    manufactured_monodomain_1d3d_conformance_target,
    manufactured_monodomain_pseudo_ecg_conformance_target,
    niederer2011_conformance_target,
    manufactured_eikonal_ecg_conformance_target,
    restitution_curves_conformance_target,
    single_cell_conformance_target,
)

pytestmark = pytest.mark.native

_TARGETS = {
    "restitutionCurves": restitution_curves_conformance_target,
    "manufacturedBidomain": manufactured_bidomain_conformance_target,
    "niederer2011": niederer2011_conformance_target,
    "manufacturedEikonalECG": manufactured_eikonal_ecg_conformance_target,
    "manufacturedBathBidomain": manufactured_bath_bidomain_conformance_target,
    "singleCell": single_cell_conformance_target,
    "manufacturedMonodomainPseudoECG": manufactured_monodomain_pseudo_ecg_conformance_target,
    "cable1DRestitution": cable_1d_restitution_conformance_target,
    "cable1DCVConvergence": cable_1d_cv_convergence_conformance_target,
    "manufacturedMonodomain1D3D": manufactured_monodomain_1d3d_conformance_target,
}


@pytest.fixture(autouse=True)
def _real_preflight(monkeypatch):
    monkeypatch.delenv("SKIP_ENV_DIAGNOSTICS", raising=False)


@pytest.mark.parametrize("record", sorted(_TARGETS))
@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_record_passes(record, check_id, tmp_path):
    verdict = run_check(check_id, _TARGETS[record](tmp_path))
    assert verdict.passed, verdict.detail
