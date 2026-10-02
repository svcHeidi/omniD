"""Every cardiacFOAM record in ``TARGETS`` passes every conformance check against the real binary.
C9 is OpenFOAM's preflight, which the suite stubs out, so this module keeps it."""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiacfoam_native import TARGETS, conformance_target

pytestmark = [pytest.mark.native, pytest.mark.usefixtures("real_preflight")]


@pytest.mark.parametrize("record", sorted(TARGETS))
@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_record_passes(record, check_id, tmp_path):
    verdict = run_check(check_id, conformance_target(record, tmp_path))
    assert verdict.passed, verdict.detail
