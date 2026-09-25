"""openCARP passes the conformance suite against the real binary and openCARP's own tutorial."""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from opencarp_native import niederer_conformance_target

pytestmark = pytest.mark.native


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_niederer_passes(check_id, tmp_path):
    verdict = run_check(check_id, niederer_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail
