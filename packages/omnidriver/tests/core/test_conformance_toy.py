"""The conformance suite over the toy target (core-alone and wheel shapes).

Every check must pass for the toy. Checks with a known historical defect
also get a deliberately broken plugin, to prove the check bites.
"""
from __future__ import annotations

import pytest

from omnidriver.conformance import run_check
from omnidriver.core.runtime.sweep_runner import _child_reconciliation
from plugins.conformance_toy import NO_CONSUMES_PLUGIN, REPLACING_PLUGIN, toy_conformance_target


@pytest.mark.parametrize("check_id", ["C1", "C2", "C3", "C5", "C6", "C7", "C8"])
def test_toy_passes(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail


def test_c8_bites_a_record_that_declares_no_inputs(tmp_path):
    verdict = run_check("C8", toy_conformance_target(tmp_path, plugin=NO_CONSUMES_PLUGIN))
    assert not verdict.passed
    assert "consumes" in verdict.detail


def test_child_reconciliation_reads_the_run_payload():
    assert _child_reconciliation('{"artifact_reconciliation": {"missing_count": 0}}') == {"missing_count": 0}
    assert _child_reconciliation("not json") is None
    assert _child_reconciliation('{"status": "ok"}') is None


def test_toy_passes_c4(tmp_path):
    verdict = run_check("C4", toy_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail


def test_c4_bites_a_renderer_that_replaces_the_document(tmp_path):
    """The P2 class of defect: a renderer that writes only the patched keys."""
    verdict = run_check("C4", toy_conformance_target(tmp_path, plugin=REPLACING_PLUGIN))
    assert not verdict.passed
    assert "label" in verdict.detail
