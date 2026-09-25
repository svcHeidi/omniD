"""The conformance suite over the toy target (core-alone and wheel shapes).

Every check must pass for the toy. Checks with a known historical defect
also get a deliberately broken plugin, to prove the check bites.
"""
from __future__ import annotations

import pytest

from omnidriver.conformance import run_check
from plugins.conformance_toy import toy_conformance_target


@pytest.mark.parametrize("check_id", ["C1", "C2", "C3"])
def test_toy_passes(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail
