"""The conformance suite over the toy target (core-alone and wheel shapes).

Every check must pass for the toy. Checks with a known historical defect
also get a deliberately broken plugin, to prove the check bites.
"""
from __future__ import annotations

import dataclasses

import pytest

from omnidriver.conformance import CHECKS, run_check
from omnidriver.core.runtime.sweep_runner import _child_reconciliation
from plugins.conformance_toy import (
    GHOST_CONSUMES_PLUGIN, NO_CONSUMES_PLUGIN, REPLACING_PLUGIN, toy_conformance_target,
)


@pytest.mark.parametrize("check_id", ["C1", "C2", "C3", "C5", "C6", "C7", "C8", "C9"])
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


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_check_that_cannot_run_is_a_failed_verdict(check_id, tmp_path):
    """I3: a misnamed record yields a failed verdict naming why, never a raise
    that would abort a runner looping over CHECKS."""
    target = dataclasses.replace(toy_conformance_target(tmp_path), record="nope")
    verdict = run_check(check_id, target)
    assert not verdict.passed
    assert "nope" in verdict.detail


def test_an_unknown_check_id_still_raises(tmp_path):
    with pytest.raises(KeyError, match="C99"):
        run_check("C99", toy_conformance_target(tmp_path))


def test_c8_bites_a_consumed_file_that_does_not_exist(tmp_path):
    """I1: enumerate_case_inputs lists every consumed path, even a missing
    one (strength ``unavailable``), so listing alone proves nothing."""
    verdict = run_check("C8", toy_conformance_target(tmp_path, plugin=GHOST_CONSUMES_PLUGIN))
    assert not verdict.passed
    assert "does/not/exist.json" in verdict.detail
    assert "constant/mesh.json" not in verdict.detail


def test_scratch_environment_is_serialised_across_threads(tmp_path, monkeypatch):
    """I2: the scratch override is process-global. A second thread must wait
    for the first to leave, and the variable is restored afterwards."""
    import os
    import threading

    from omnidriver.conformance.checks import _SCRATCH_VARIABLE, _scratch_environment

    monkeypatch.delenv(_SCRATCH_VARIABLE, raising=False)
    first = toy_conformance_target(tmp_path / "a")
    second = toy_conformance_target(tmp_path / "b")
    first_inside, release_first = threading.Event(), threading.Event()
    seen: list[str | None] = []

    def hold_first():
        with _scratch_environment(first):
            first_inside.set()
            release_first.wait(5)

    def enter_second():
        with _scratch_environment(second):
            seen.append(os.environ.get(_SCRATCH_VARIABLE))

    holder = threading.Thread(target=hold_first)
    holder.start()
    assert first_inside.wait(5)
    waiter = threading.Thread(target=enter_second)
    waiter.start()
    waiter.join(0.3)
    assert waiter.is_alive(), "a second thread entered while the first held the scratch override"
    release_first.set()
    holder.join(5)
    waiter.join(5)
    assert seen == [str(second.scratch_root)]
    assert _SCRATCH_VARIABLE not in os.environ
