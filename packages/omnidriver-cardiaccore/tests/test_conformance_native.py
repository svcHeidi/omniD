"""Every cardiacCore tutorial record passes the conformance suite (every
check in ``CHECKS``), against the real cardiacCore utilities, the native
tree, and the supplied anatomy bundle."""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiaccore_native import TARGETS, conformance_target

pytestmark = pytest.mark.native_cardiaccore


@pytest.mark.parametrize("record", sorted(TARGETS))
@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_record_passes(record, check_id, tmp_path):
    verdict = run_check(check_id, conformance_target(record, tmp_path))
    assert verdict.passed, verdict.detail
