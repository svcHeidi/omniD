"""openCARP passes the conformance suite against the real binary and openCARP's own tutorial."""
from __future__ import annotations

import pytest

from omnidriver.conformance import CHECKS, run_check
from opencarp_native import niederer_conformance_target

pytestmark = pytest.mark.native_opencarp


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_niederer_passes(check_id, tmp_path):
    verdict = run_check(check_id, niederer_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail


def test_no_token_survives_in_workflow_logs(tmp_path):
    """G3/K9: openCARP prints a CI token in every run header; kept logs must not carry it."""
    target = niederer_conformance_target(tmp_path)
    assert run_check("C6", target).passed
    logs = list(target.scratch_root.rglob("workflow_logs/*.log"))
    assert logs, "C6 wrote no step logs"
    texts = [p.read_text(errors="ignore") for p in logs]
    assert not [p for p, t in zip(logs, texts) if "gitlab-ci-token" in t]
    assert any("[REDACTED]@" in t for t in texts), "the build header's URL was not redacted where it appears"
