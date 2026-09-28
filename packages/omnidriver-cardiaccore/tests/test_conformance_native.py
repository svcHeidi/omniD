"""cardiacCore's ``humanSlab`` record passes the conformance suite, every
check in ``CHECKS``, against the real cardiacCore utilities, the native
tree, and the owner's anatomy bundle (step S, S3's own proof point:
docs/superpowers/specs/2026-09-28-supplied-inputs-design.md, table row S3).
"""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiaccore_native import human_slab_conformance_target

pytestmark = pytest.mark.native_cardiaccore


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_human_slab_passes(check_id, tmp_path):
    verdict = run_check(check_id, human_slab_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail
