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
    NO_CONSUMES_PLUGIN, NO_PRODUCES_PLUGIN, OVER_GENERATED_CONVENTIONS_PLUGIN, REPLACING_PLUGIN,
    SILENT_PREFLIGHT_PLUGIN, SILENT_SURFACE_PLUGIN, UNDECLARED_OUTPUT_PLUGIN, UNLISTED_KEY_PLUGIN,
    STRAY_NAME, STRAY_ROOT_VARIABLE, toy_conformance_target,
)
from plugins.quantity_toy import BAD_DECLARATION_PLUGIN, QUANTITY_TOY_PLUGIN, UNREADABLE_PLUGIN


@pytest.mark.parametrize("check_id", ["C1", "C2", "C3", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12"])
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


def test_checks_take_the_scratch_root_as_an_argument_so_threads_do_not_interleave(tmp_path, monkeypatch):
    """Replaces the I2 lock test (2026-09-26). Checks used to point core at
    the target's scratch root by overriding ``OMNIDRIVER_SCRATCH_DIR`` in
    ``os.environ`` behind a lock. Core takes the scratch root as an argument
    now, so two targets planned in parallel threads each stage under their
    own scratch root, and the process environment is never written."""
    import os
    import threading

    from omnidriver.core.specs.paths import SCRATCH_ENV_VAR

    monkeypatch.delenv(SCRATCH_ENV_VAR, raising=False)
    targets = [toy_conformance_target(tmp_path / name) for name in ("a", "b")]
    barrier = threading.Barrier(len(targets))
    verdicts: dict[str, object] = {}
    seen_in_environment: list[str | None] = []

    def plan(target):
        barrier.wait(5)
        verdicts[str(target.scratch_root)] = run_check("C5", target)
        seen_in_environment.append(os.environ.get(SCRATCH_ENV_VAR))

    threads = [threading.Thread(target=plan, args=(t,)) for t in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    for target in targets:
        verdict = verdicts[str(target.scratch_root)]
        assert verdict.passed, verdict.detail
        assert (target.scratch_root / "records" / target.record).is_dir()
    assert seen_in_environment == [None, None]
    assert SCRATCH_ENV_VAR not in os.environ


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


@pytest.mark.parametrize("scratch_dir", ["touch", "my touch runs", "the 'touch' runs", 'a "touch" dir'])
def test_c9_is_not_satisfied_by_the_solver_name_in_the_echoed_scratch_path_S_I2(tmp_path, scratch_dir):
    """Final review S-I2 (A-M5, W2-M2): C9 matched ``solver_command in m``, so
    a preflight that never names the solver passed whenever the PATH it
    echoed -- under the scratch root -- contained the solver's name, e.g.
    ``~/openCARP-runs/``. C9 now drops that PATH from each message and
    requires the command as a quoted token."""
    from plugins.conformance_toy import AUXILIARY_ONLY_PREFLIGHT_PLUGIN

    target = toy_conformance_target(tmp_path, plugin=AUXILIARY_ONLY_PREFLIGHT_PLUGIN)
    target = dataclasses.replace(target, scratch_root=tmp_path / scratch_dir / "scratch")
    verdict = run_check("C9", target)
    assert not verdict.passed, verdict.detail
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


@pytest.mark.parametrize("check_id", ["C5", "C6", "C7"])
def test_a_record_plugin_without_the_runnable_hook_passes_I4(check_id, tmp_path):
    """Wave-2 review I4: core's run-document gate asked the plugin whether a
    case "without driver-owned workflow metadata" is runnable -- the wrong
    question for a record run, whose document carries the record's own
    steps. openCARP and the toy answered it only to get past the gate."""
    from plugins.conformance_toy import NO_RUNNABLE_HOOK_PLUGIN

    verdict = run_check(check_id, toy_conformance_target(tmp_path, plugin=NO_RUNNABLE_HOOK_PLUGIN))
    assert verdict.passed, verdict.detail


def test_c11_names_an_output_the_record_does_not_declare(tmp_path):
    verdict = run_check("C11", toy_conformance_target(tmp_path, plugin=UNDECLARED_OUTPUT_PLUGIN))
    assert not verdict.passed
    assert "undeclared.out" in verdict.detail
    assert "workflow_state.json" not in verdict.detail   # core's own records are never carried


def test_c11_names_an_authored_path_wrongly_dropped(tmp_path):
    """R1 fix, finding M1: C11 used to assert ``restaged <= native`` only,
    so a plugin whose conventions wrongly claim an authored native file is
    "generated" -- and so get dropped during staging -- passed cleanly.
    It is now checked both ways."""
    verdict = run_check(
        "C11", toy_conformance_target(tmp_path, plugin=OVER_GENERATED_CONVENTIONS_PLUGIN),
    )
    assert not verdict.passed
    assert "mesh.json" in verdict.detail
    assert "dropped" in verdict.detail


def test_c12_passes_a_record_whose_formats_have_readers(tmp_path):
    target = dataclasses.replace(toy_conformance_target(tmp_path), plugin=QUANTITY_TOY_PLUGIN, record="toyQuantities")
    verdict = run_check("C12", target)
    assert verdict.passed, verdict.detail
    assert "toy_named_values" in verdict.detail


def test_c12_says_so_when_nothing_declares_a_format(tmp_path):
    verdict = run_check("C12", toy_conformance_target(tmp_path))
    assert verdict.passed and "nothing to read" in verdict.detail


@pytest.mark.parametrize(("plugin", "named"), [(UNREADABLE_PLUGIN, "no reader"), (BAD_DECLARATION_PLUGIN, "furlong")])
def test_c12_bites_a_declared_format_it_cannot_read(plugin, named, tmp_path):
    verdict = run_check("C12", toy_conformance_target(tmp_path, plugin=plugin))
    assert not verdict.passed
    assert named in verdict.detail and "toy_unreadable" in verdict.detail
