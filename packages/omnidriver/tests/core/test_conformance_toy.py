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
    DOCUMENTED_PLUGIN, GHOST_CONSUMES_PLUGIN, INDEXED_KEY_PLUGIN, KINDLESS_KEY_PLUGIN, NATIVE_WRITING_PLUGIN,
    NO_CONSUMES_PLUGIN, NO_PRODUCES_PLUGIN, REPLACING_PLUGIN, SILENT_PREFLIGHT_PLUGIN,
    SILENT_SURFACE_PLUGIN, UNLISTED_KEY_PLUGIN,
    STRAY_NAME, STRAY_ROOT_VARIABLE, toy_conformance_target,
)


@pytest.mark.parametrize("check_id", ["C1", "C2", "C3", "C5", "C6", "C7", "C8", "C9", "C10"])
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


def test_a_write_into_the_native_cases_root_fails_the_check(tmp_path):
    """I4: the suite-wide guard watches all of cases_root, not only the
    record's subtree that C7 digests."""
    target = toy_conformance_target(tmp_path, plugin=NATIVE_WRITING_PLUGIN)
    target = dataclasses.replace(
        target, environment={**target.environment, STRAY_ROOT_VARIABLE: str(target.cases_root)},
    )
    verdict = run_check("C7", target)
    assert not verdict.passed
    assert STRAY_NAME in verdict.detail


def test_the_default_timeout_keeps_existing_constructions_working(tmp_path):
    assert toy_conformance_target(tmp_path).timeout_s == 600.0


@pytest.mark.parametrize("check_id", ["C6", "C7"])
def test_a_child_that_outlives_the_timeout_is_a_failed_verdict(check_id, tmp_path):
    """I5: a hung solver must still yield a verdict, naming the timeout."""
    target = dataclasses.replace(toy_conformance_target(tmp_path), timeout_s=0.001)
    verdict = run_check(check_id, target)
    assert not verdict.passed
    assert "timed out after 0.001" in verdict.detail


def test_the_sweep_passes_the_timeout_per_case(tmp_path, monkeypatch):
    import subprocess

    from omnidriver.conformance import checks

    calls = []

    def spy(argv, **kwargs):
        calls.append((argv, kwargs))
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(checks.subprocess, "run", spy)
    run_check("C7", dataclasses.replace(toy_conformance_target(tmp_path), timeout_s=42.0))
    [(argv, kwargs)] = calls
    assert kwargs["timeout"] == 42.0
    assert argv[argv.index("--case-timeout-s") + 1] == "42.0"


@pytest.mark.parametrize("inside", [".", "scratch", "toyTutorial/scratch"])
def test_a_scratch_root_inside_the_native_tree_is_refused(inside, tmp_path):
    """M8: every stage, plan and rmtree lands under scratch_root."""
    target = toy_conformance_target(tmp_path)
    scratch = target.cases_root / inside
    with pytest.raises(ValueError) as excinfo:
        dataclasses.replace(target, scratch_root=scratch)
    assert str(scratch) in str(excinfo.value)
    assert str(target.cases_root) in str(excinfo.value)


_RECONCILIATION_WITH_AN_ABSENT_OPTIONAL = {
    "missing_count": 1,
    "artifacts": [
        {"artifact_id": "record.solve.0", "status": "matched", "optional": False},
        {"artifact_id": "extra.optional", "status": "missing", "optional": True},
    ],
}
_CANNED_CHILD_OUTPUT = {
    "C6": {"status": "ok", "artifact_reconciliation": _RECONCILIATION_WITH_AN_ABSENT_OPTIONAL},
    "C7": {"completed_count": 2, "failed_count": 0, "cases": [
        {"case_id": case_id, "artifact_reconciliation": _RECONCILIATION_WITH_AN_ABSENT_OPTIONAL}
        for case_id in ("a", "b")
    ]},
}


@pytest.mark.parametrize("check_id", ["C6", "C7"])
def test_an_absent_optional_artifact_fails_neither_run_check(check_id, tmp_path, monkeypatch):
    """M3: C6 and C7 treat optional artifacts the same way."""
    import json
    import subprocess

    from omnidriver.conformance import checks

    def canned(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_CANNED_CHILD_OUTPUT[check_id]), stderr="")

    monkeypatch.setattr(checks.subprocess, "run", canned)
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail


@pytest.mark.parametrize("check_id", ["C6", "C7"])
def test_an_absent_required_artifact_fails_both_run_checks(check_id, tmp_path, monkeypatch):
    import copy
    import json
    import subprocess

    from omnidriver.conformance import checks

    output = copy.deepcopy(_CANNED_CHILD_OUTPUT[check_id])
    for rec in [output.get("artifact_reconciliation")] + [c["artifact_reconciliation"] for c in output.get("cases", ())]:
        if rec is not None:
            rec["artifacts"][0]["status"] = "missing"

    def canned(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(output), stderr="")

    monkeypatch.setattr(checks.subprocess, "run", canned)
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert not verdict.passed
    assert "record.solve.0" in verdict.detail


@pytest.mark.parametrize(("message", "name", "named"), [
    ("'cell_count' is neither a 'document:dotted.path' key nor an axis", "cell_count", True),
    ("validating constant/mesh.json:nope raised KeyError", "constant/mesh.json:nope", True),
    ('unknown key "constant/mesh.json:nope".', "constant/mesh.json:nope", True),
    ("unknown study name `x`", "x", True),
    ("refused constant/mesh.json:nope.", "constant/mesh.json:nope", True),
    # M6: a bare substring is not naming it.
    ("refused: 'xy' is not an axis", "x", False),
    ("cell_count_v2 is unknown", "cell_count", False),
    ("refused constant/mesh.json:nopes", "constant/mesh.json:nope", False),
    ("refused other/constant/mesh.json:nope", "constant/mesh.json:nope", False),
    ("refused constant/mesh.json:nope.inner", "constant/mesh.json:nope", False),
])
def test_c3_requires_the_refusal_to_name_the_unknown_study_exactly(message, name, named):
    from omnidriver.conformance.checks import _names

    assert _names(message, name) is named


def test_c6_bites_a_record_that_declares_no_outputs(tmp_path):
    """M7."""
    verdict = run_check("C6", toy_conformance_target(tmp_path, plugin=NO_PRODUCES_PLUGIN))
    assert not verdict.passed
    assert "produces" in verdict.detail


def test_c9_bites_a_preflight_that_never_reports_a_missing_solver(tmp_path):
    """M7."""
    verdict = run_check("C9", toy_conformance_target(tmp_path, plugin=SILENT_PREFLIGHT_PLUGIN))
    assert not verdict.passed
    assert "'touch' off PATH" in verdict.detail


def test_c10_surface_lists_the_toy_axis_key_and_guidance(tmp_path):
    from omnidriver.core.introspection import describe_entry
    from omnidriver.core.plugin_interface import load_plugin_context

    target = toy_conformance_target(tmp_path)
    payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)},
                             driver_context=load_plugin_context(target.plugin))
    surface = payload["record_surface"]
    assert surface["axes"] == [{"name": "number_cells", "value_kind": "integer"}]
    assert {"document": "constant/mesh.json", "key": "cells", "value_kind": "integer"} in [
        {k: e[k] for k in ("document", "key", "value_kind")} for e in surface["keys"]]
    assert surface["guidance"] and surface["guidance"][0]["title"]


def test_c10_bites_a_stack_that_declares_no_surface(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=SILENT_SURFACE_PLUGIN))
    assert not verdict.passed
    assert "no key catalogue" in verdict.detail
    assert "no agent guidance" in verdict.detail


def test_c10_bites_a_catalogue_without_the_targets_own_key(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=UNLISTED_KEY_PLUGIN))
    assert not verdict.passed
    assert "constant/mesh.json:cells is not in the catalogue" in verdict.detail


def test_c10_matches_a_concrete_index_against_its_int_template(tmp_path):
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=INDEXED_KEY_PLUGIN), patch=("constant/mesh.json:cells[3].count", 7),
    )
    verdict = run_check("C10", target)
    assert verdict.passed, verdict.detail


def test_c10_surface_carries_the_cases_own_documentation(tmp_path):
    from omnidriver.core.introspection import describe_entry
    from omnidriver.core.plugin_interface import load_plugin_context

    target = toy_conformance_target(tmp_path, plugin=DOCUMENTED_PLUGIN)
    (target.cases_root / "toyTutorial" / "README.md").write_text("# toyTutorial\nRead me first.\n")
    payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)},
                             driver_context=load_plugin_context(target.plugin))
    assert payload["record_surface"]["case_documentation"] == [
        {"path": "README.md", "text": "# toyTutorial\nRead me first.\n"},
    ]


def test_c10_bites_a_catalogue_entry_without_a_value_kind(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=KINDLESS_KEY_PLUGIN))
    assert not verdict.passed
    assert "'key': 'label'" in verdict.detail
