"""cardiacCore's ``humanSlab`` record passes the conformance suite, every
check in ``CHECKS``, against the real cardiacCore utilities, the native
tree, and the owner's anatomy bundle (step S, S3's own proof point:
docs/superpowers/specs/2026-09-28-supplied-inputs-design.md, table row S3).
"""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from cardiaccore_native import (
    human_slab_conformance_target,
    idealized_heart_conformance_target,
    idealized_heart_endocardial_conformance_target,
    idealized_heart_pig_transmural_conformance_target,
)

pytestmark = pytest.mark.native_cardiaccore

_TARGETS = {
    "humanSlab": human_slab_conformance_target,
    "idealizedHeart": idealized_heart_conformance_target,
    "idealizedHeartEndocardial": idealized_heart_endocardial_conformance_target,
    "idealizedHeartPigTransmural": idealized_heart_pig_transmural_conformance_target,
}


@pytest.mark.parametrize("record", sorted(_TARGETS))
@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_record_passes(record, check_id, tmp_path):
    verdict = run_check(check_id, _TARGETS[record](tmp_path))
    assert verdict.passed, verdict.detail
