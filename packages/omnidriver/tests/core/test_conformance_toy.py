"""The conformance suite over the toy target (core-alone and wheel shapes).

Every check must pass for the toy. Checks with a known historical defect
also get a deliberately broken plugin, to prove the check bites.
"""
from __future__ import annotations

import dataclasses

import pytest

from omnidriver.conformance import CHECKS, run_check
from plugins.toy import (
    ACCEPTING_PLUGIN, BROKEN_RULE_PLUGIN,
    DEFAULT_ARGUMENT_MARKER, DEFAULT_ARGUMENT_PLUGIN, DEFAULT_ROUTE_MARKER, DEFAULT_ROUTE_PLUGIN, DOCUMENTED_PLUGIN, GHOST_CONSUMES_PLUGIN, INDEXED_KEY_PLUGIN, KINDLESS_KEY_PLUGIN, NAMED_KEY_PLUGIN,
    NATIVE_WRITING_PLUGIN, NO_CONSUMES_PLUGIN, NO_PRODUCES_PLUGIN, OPEN_DOCUMENT_PLUGIN, OTHER_OPEN_DOCUMENT_PLUGIN,
    OVER_GENERATED_CONVENTIONS_PLUGIN, PREDICTED_FORMAT_PLUGIN, REPLACING_PLUGIN, SILENT_PREFLIGHT_PLUGIN, SILENT_SURFACE_PLUGIN,
    UNDECLARED_OUTPUT_PLUGIN, UNLISTED_KEY_PLUGIN, VALIDATED_KINDLESS_PLUGIN,
    REORDERING_PARALLEL_PLUGIN, SERIAL_PARALLEL_PLUGIN, SINGLE_RANK_PLUGIN,
    STRAY_NAME, STRAY_ROOT_VARIABLE, quantity_toy_conformance_target, toy_conformance_target,
    toy_conformance_target_with_input,
)
from plugins.toy import BAD_DECLARATION_PLUGIN, QUANTITY_TOY_PLUGIN, UNREADABLE_PLUGIN


#: The toy proposes no patch from an empty study, declares no output format and no quantity, so these
#: verify nothing for it and are reported apart from the checks that passed.
TOY_NOT_APPLICABLE = {"C2", "C12", "C13", "C14"}


def _toy_status(check_id):
    return "not_applicable" if check_id in TOY_NOT_APPLICABLE else "passed"


@pytest.mark.parametrize("check_id", ["C1", "C3", "C5", "C6", "C7", "C8", "C9", "C10", "C11"])
def test_toy_passes(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == "passed", verdict.detail


@pytest.mark.parametrize("check_id", sorted(TOY_NOT_APPLICABLE))
def test_a_check_that_verifies_nothing_for_the_toy_is_not_applicable_and_says_why(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == "not_applicable", verdict.detail
    assert any(word in verdict.detail for word in ("no patches", "no workflow step", "no quantity"))


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_record_with_a_supplied_input_passes(check_id, tmp_path):
    """A toy record with a supplied bundle passes C1-C14 in core, no native tree or solver needed."""
    verdict = run_check(check_id, toy_conformance_target_with_input(tmp_path))
    assert verdict.status == _toy_status(check_id), verdict.detail


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_record_with_a_default_route_passes_with_no_study_values(check_id, tmp_path):
    """A record with two routes and a ``default_variant`` is a full conformance target with an empty base study."""
    verdict = run_check(check_id, toy_conformance_target(tmp_path, plugin=DEFAULT_ROUTE_PLUGIN))
    assert verdict.status == _toy_status(check_id), verdict.detail
    if check_id == "C6":
        assert "1 declared artifact(s) present" in verdict.detail


def test_the_default_route_is_the_one_that_runs(tmp_path):
    """C6 counts declared artifacts of the selected route only; this checks by name that the route which ran is the native one, not the other."""
    from omnidriver.conformance.checks import _context, _plan

    target = toy_conformance_target(tmp_path, plugin=DEFAULT_ROUTE_PLUGIN)
    report = _plan(target, _context(target))
    assert report.status == "ok"
    steps = report.run_document.to_json()["workflowDag"]["steps"]
    assert [(s["id"], s["command"], s["args"]) for s in steps] == [
        ("solveNative", "touch", [DEFAULT_ROUTE_MARKER]),
    ]


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_record_whose_step_has_a_default_argument_passes(check_id, tmp_path):
    """A step's default argument is fixed on the step and needs no study value."""
    verdict = run_check(check_id, toy_conformance_target(tmp_path, plugin=DEFAULT_ARGUMENT_PLUGIN))
    assert verdict.status == _toy_status(check_id), verdict.detail


def test_an_axis_argument_replaces_the_default_in_the_planned_command(tmp_path):
    import dataclasses as _dc

    from omnidriver.conformance.checks import _context, _plan

    target = toy_conformance_target(tmp_path, plugin=DEFAULT_ARGUMENT_PLUGIN)
    ctx = _context(target)
    default = _plan(target, ctx).run_document.to_json()["workflowDag"]["steps"][0]
    assert default["args"] == ["-c", 'touch "$2"', "sh", "--marker", DEFAULT_ARGUMENT_MARKER]
    replaced = _plan(_dc.replace(target, base_study={"marker": "axis"}), ctx).run_document.to_json()
    assert replaced["workflowDag"]["steps"][0]["args"] == ["-c", 'touch "$2"', "sh", "--marker", "axis.marker"]


def test_c8_bites_a_record_that_declares_no_inputs(tmp_path):
    verdict = run_check("C8", toy_conformance_target(tmp_path, plugin=NO_CONSUMES_PLUGIN))
    assert verdict.status == "failed"
    assert "consumes" in verdict.detail


def test_toy_passes_c4(tmp_path):
    verdict = run_check("C4", toy_conformance_target(tmp_path))
    assert verdict.status == "passed", verdict.detail


def test_c4_bites_a_renderer_that_replaces_the_document(tmp_path):
    """A renderer that writes only the patched keys."""
    verdict = run_check("C4", toy_conformance_target(tmp_path, plugin=REPLACING_PLUGIN))
    assert verdict.status == "failed"
    assert "label" in verdict.detail


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_check_that_cannot_run_is_a_failed_verdict(check_id, tmp_path):
    """A misnamed record yields a failed verdict naming why, never a raise that would abort a runner looping over CHECKS."""
    target = dataclasses.replace(toy_conformance_target(tmp_path), record="nope")
    verdict = run_check(check_id, target)
    assert verdict.status == "failed"
    assert "nope" in verdict.detail


def test_an_unknown_check_id_still_raises(tmp_path):
    with pytest.raises(KeyError, match="C99"):
        run_check("C99", toy_conformance_target(tmp_path))


def test_c8_bites_a_consumed_file_that_does_not_exist(tmp_path):
    """enumerate_case_inputs lists every consumed path, even a missing one (strength ``unavailable``), so listing alone proves nothing."""
    verdict = run_check("C8", toy_conformance_target(tmp_path, plugin=GHOST_CONSUMES_PLUGIN))
    assert verdict.status == "failed"
    assert "does/not/exist.json" in verdict.detail
    assert "constant/mesh.json" not in verdict.detail


def test_checks_take_the_scratch_root_as_an_argument_so_threads_do_not_interleave(tmp_path, monkeypatch):
    """The scratch root is a check argument, so concurrent checks do not interleave."""
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
        assert verdict.status == "passed", verdict.detail
        assert (target.scratch_root / "records" / target.record).is_dir()
    assert seen_in_environment == [None, None]
    assert SCRATCH_ENV_VAR not in os.environ


def test_a_write_into_the_native_cases_root_fails_the_check(tmp_path, monkeypatch):
    """The suite-wide guard watches all of cases_root, not only the record's subtree that C7 digests."""
    target = toy_conformance_target(tmp_path, plugin=NATIVE_WRITING_PLUGIN)
    monkeypatch.setenv(STRAY_ROOT_VARIABLE, str(target.cases_root))
    verdict = run_check("C7", target)
    assert verdict.status == "failed"
    assert STRAY_NAME in verdict.detail


def test_the_default_timeout_keeps_existing_constructions_working(tmp_path):
    assert toy_conformance_target(tmp_path).timeout_s == 600.0


@pytest.mark.parametrize("check_id", ["C6", "C7"])
def test_a_child_that_outlives_the_timeout_is_a_failed_verdict(check_id, tmp_path):
    """A hung solver must still yield a verdict, naming the timeout."""
    target = dataclasses.replace(toy_conformance_target(tmp_path), timeout_s=0.001)
    verdict = run_check(check_id, target)
    assert verdict.status == "failed"
    assert "timed out after 0.001" in verdict.detail


def test_the_sweep_passes_the_timeout_per_case(tmp_path, monkeypatch):
    import subprocess

    from omnidriver.conformance import checks, harness

    calls = []

    def spy(argv, **kwargs):
        calls.append((argv, kwargs))
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(harness, "run_child", spy)
    run_check("C7", dataclasses.replace(toy_conformance_target(tmp_path), timeout_s=42.0))
    [(argv, kwargs)] = calls
    assert kwargs["timeout"] == 42.0
    assert argv[argv.index("--case-timeout-s") + 1] == "42.0"


def test_a_conformance_run_gives_its_state_file_so_a_timeout_ends_the_step_too(tmp_path, monkeypatch):
    import subprocess

    from omnidriver.conformance import checks

    calls = []

    def spy(argv, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(checks, "run_child", spy)
    run_check("C6", toy_conformance_target(tmp_path))
    [kwargs] = calls
    assert kwargs["state_path"].name == "workflow_state.json"


@pytest.mark.parametrize("inside", [".", "scratch", "toyTutorial/scratch"])
def test_a_scratch_root_inside_the_native_tree_is_refused(inside, tmp_path):
    """Every stage, plan and rmtree lands under scratch_root."""
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
    """C6 and C7 treat optional artifacts the same way."""
    import json
    import subprocess

    from omnidriver.conformance import checks, harness

    def canned(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_CANNED_CHILD_OUTPUT[check_id]), stderr="")

    monkeypatch.setattr(checks, "run_child", canned)
    monkeypatch.setattr(harness, "run_child", canned)
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == "passed", verdict.detail


@pytest.mark.parametrize("check_id", ["C6", "C7"])
def test_an_absent_required_artifact_fails_both_run_checks(check_id, tmp_path, monkeypatch):
    import copy
    import json
    import subprocess

    from omnidriver.conformance import checks, harness

    output = copy.deepcopy(_CANNED_CHILD_OUTPUT[check_id])
    for rec in [output.get("artifact_reconciliation")] + [c["artifact_reconciliation"] for c in output.get("cases", ())]:
        if rec is not None:
            rec["artifacts"][0]["status"] = "missing"

    def canned(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(output), stderr="")

    monkeypatch.setattr(checks, "run_child", canned)
    monkeypatch.setattr(harness, "run_child", canned)
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == "failed"
    assert "record.solve.0" in verdict.detail


@pytest.mark.parametrize(("message", "name", "named"), [
    ("'cell_count' is neither a 'document:dotted.path' key nor an axis", "cell_count", True),
    ("validating constant/mesh.json:nope raised KeyError", "constant/mesh.json:nope", True),
    ('unknown key "constant/mesh.json:nope".', "constant/mesh.json:nope", True),
    ("unknown study name `x`", "x", True),
    ("refused constant/mesh.json:nope.", "constant/mesh.json:nope", True),
    # A bare substring is not naming it.
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
    """A record that declares no outputs fails C6."""
    verdict = run_check("C6", toy_conformance_target(tmp_path, plugin=NO_PRODUCES_PLUGIN))
    assert verdict.status == "failed"
    assert "produces" in verdict.detail


def test_c9_bites_a_preflight_that_never_reports_a_missing_solver(tmp_path):
    verdict = run_check("C9", toy_conformance_target(tmp_path, plugin=SILENT_PREFLIGHT_PLUGIN))
    assert verdict.status == "failed"
    assert "'touch' off PATH" in verdict.detail


@pytest.mark.parametrize("scratch_dir", ["touch", "my touch runs", "the 'touch' runs", 'a "touch" dir'])
def test_c9_is_not_satisfied_by_the_solver_name_in_the_echoed_scratch_path_S_I2(tmp_path, scratch_dir):
    """A preflight that never names the solver must not pass just because the scratch path it echoes happens to contain the solver's name."""
    from plugins.toy import AUXILIARY_ONLY_PREFLIGHT_PLUGIN

    target = toy_conformance_target(tmp_path, plugin=AUXILIARY_ONLY_PREFLIGHT_PLUGIN)
    target = dataclasses.replace(target, scratch_root=tmp_path / scratch_dir / "scratch")
    verdict = run_check("C9", target)
    assert verdict.status == "failed", verdict.detail
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


def test_describe_of_a_record_carries_its_keys_only_in_the_record_surface(tmp_path):
    """One canonical catalogue for a record: `record_surface.keys`, never `dict_entries` beside it."""
    from omnidriver.core.introspection import describe_entry
    from omnidriver.core.plugin_interface import load_plugin_context

    target = toy_conformance_target(tmp_path)
    payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)},
                             driver_context=load_plugin_context(target.plugin))
    assert "dict_entries" not in payload
    assert payload["record_surface"]["keys"]


def test_c10_bites_a_stack_that_declares_no_surface(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=SILENT_SURFACE_PLUGIN))
    assert verdict.status == "failed"
    assert "no key catalogue" in verdict.detail
    assert "no agent guidance" in verdict.detail


def _break_the_surface(monkeypatch, breaker):
    """Wrap core's ``record_surface`` so the ``describe`` C10 reads lists a deliberately wrong axis set."""
    from omnidriver.core.runtime import record_surface as module

    real = module.record_surface

    def broken(*args, **kwargs):
        surface = real(*args, **kwargs)
        surface["axes"] = breaker(surface["axes"])
        return surface

    monkeypatch.setattr(module, "record_surface", broken)


def test_c10_bites_a_surface_that_drops_an_axis(tmp_path, monkeypatch):
    _break_the_surface(monkeypatch, lambda axes: [])
    verdict = run_check("C10", toy_conformance_target(tmp_path))
    assert verdict.status == "failed", verdict.detail
    assert "axes listed [], record declares ['number_cells']" in verdict.detail
    assert "the target's own study name(s) ['number_cells'] are not listed" in verdict.detail


def test_c10_bites_a_surface_that_lists_an_axis_under_the_wrong_kind(tmp_path, monkeypatch):
    _break_the_surface(monkeypatch, lambda axes: [{**a, "value_kind": "word"} for a in axes])
    verdict = run_check("C10", toy_conformance_target(tmp_path))
    assert verdict.status == "failed", verdict.detail
    assert "'number_cells' is listed as 'word', but its contract takes 'integer'" in verdict.detail


def test_c10_bites_a_surface_that_lists_an_axis_the_record_does_not_declare(tmp_path, monkeypatch):
    _break_the_surface(monkeypatch, lambda axes: axes + [{"name": "ghost", "value_kind": "integer"}])
    verdict = run_check("C10", toy_conformance_target(tmp_path))
    assert verdict.status == "failed", verdict.detail
    assert "axes listed ['ghost', 'number_cells'], record declares ['number_cells']" in verdict.detail


def test_c10_bites_a_catalogue_without_the_targets_own_key(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=UNLISTED_KEY_PLUGIN))
    assert verdict.status == "failed"
    assert "constant/mesh.json:cells is not in the catalogue" in verdict.detail


def test_c10_matches_a_concrete_index_against_its_int_template(tmp_path):
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=INDEXED_KEY_PLUGIN), patch=("constant/mesh.json:cells[3].count", 7),
    )
    verdict = run_check("C10", target)
    assert verdict.status == "passed", verdict.detail


@pytest.mark.parametrize(("key", "listed"), [
    ("regions.lv.count", True),
    ("regions.lv[0].count", True),     # one dot-free segment, whatever it holds
    ("regions.lv.inner.count", False),  # two segments are not one
    ("regions..count", False),          # an empty segment is not a segment
    ("regions.count", False),
])
def test_c10_matches_a_named_segment_against_its_template(key, listed, tmp_path):
    """`<region_name>` in a catalogue key stands for any single dot-free segment."""
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=NAMED_KEY_PLUGIN), patch=(f"constant/mesh.json:{key}", 7),
    )
    verdict = run_check("C10", target)
    assert (verdict.status == "passed") is listed, verdict.detail
    if not listed:
        assert f"constant/mesh.json:{key} is not in the catalogue" in verdict.detail


def test_c10_an_int_template_does_not_match_a_named_index(tmp_path):
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=INDEXED_KEY_PLUGIN), patch=("constant/mesh.json:cells[x].count", 7),
    )
    verdict = run_check("C10", target)
    assert verdict.status == "failed"
    assert "constant/mesh.json:cells[x].count is not in the catalogue" in verdict.detail


def test_c10_matches_any_key_of_an_open_document_through_its_document(tmp_path):
    """A document-level entry (``key: "<any>"``, ``validated: False``) needs no value kind, and lists every key of its document."""
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=OPEN_DOCUMENT_PLUGIN), patch=("constant/mesh.json:a.b[2].c", 7),
    )
    verdict = run_check("C10", target)
    assert verdict.status == "passed", verdict.detail


def test_c10_an_open_document_lists_only_its_own_document(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=OTHER_OPEN_DOCUMENT_PLUGIN))
    assert verdict.status == "failed"
    assert "constant/mesh.json:cells is not in the catalogue" in verdict.detail


def test_c10_bites_a_kindless_entry_that_does_not_say_it_is_unvalidated(tmp_path):
    verdict = run_check("C10", toy_conformance_target(tmp_path, plugin=VALIDATED_KINDLESS_PLUGIN))
    assert verdict.status == "failed"
    assert "'key': '<any>'" in verdict.detail


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
    assert verdict.status == "failed"
    assert "'key': 'label'" in verdict.detail


def test_c11_names_an_output_the_record_does_not_declare(tmp_path):
    verdict = run_check("C11", toy_conformance_target(tmp_path, plugin=UNDECLARED_OUTPUT_PLUGIN))
    assert verdict.status == "failed"
    assert "undeclared.out" in verdict.detail
    assert "workflow_state.json" not in verdict.detail   # core's own records are never carried


def test_c11_names_an_authored_path_wrongly_dropped(tmp_path):
    """C11 must also catch a plugin whose conventions wrongly claim an authored native file is "generated" and drop it during staging."""
    verdict = run_check(
        "C11", toy_conformance_target(tmp_path, plugin=OVER_GENERATED_CONVENTIONS_PLUGIN),
    )
    assert verdict.status == "failed"
    assert "mesh.json" in verdict.detail
    assert "dropped" in verdict.detail


def test_c12_passes_a_record_whose_formats_have_readers(tmp_path):
    target = dataclasses.replace(toy_conformance_target(tmp_path), plugin=QUANTITY_TOY_PLUGIN, record="toyQuantities")
    verdict = run_check("C12", target)
    assert verdict.status == "passed", verdict.detail
    assert "toy_named_values" in verdict.detail


def test_c12_is_not_applicable_when_no_step_declares_a_format(tmp_path):
    verdict = run_check("C12", toy_conformance_target(tmp_path))
    assert verdict.status == "not_applicable" and "no reader is expected" in verdict.detail


def test_c12_names_a_format_only_the_plan_predicts(tmp_path):
    """A format a plugin predicts and no step of the record declares is not asked to be read, and is named."""
    verdict = run_check("C12", toy_conformance_target(tmp_path, plugin=PREDICTED_FORMAT_PLUGIN))
    assert verdict.status == "not_applicable"
    assert "toy_trace" in verdict.detail and "toy_trace_format" in verdict.detail


@pytest.mark.parametrize(("plugin", "named"), [(UNREADABLE_PLUGIN, "no reader"), (BAD_DECLARATION_PLUGIN, "furlong")])
def test_c12_bites_a_declared_format_it_cannot_read(plugin, named, tmp_path):
    verdict = run_check("C12", toy_conformance_target(tmp_path, plugin=plugin))
    assert verdict.status == "failed"
    assert named in verdict.detail and "toy_unreadable" in verdict.detail


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_a_record_with_declared_quantities_passes_every_check(check_id, tmp_path):
    """Only C2 verifies nothing here: the record proposes no patch from an empty study."""
    verdict = run_check(check_id, quantity_toy_conformance_target(tmp_path))
    assert verdict.status == ("not_applicable" if check_id == "C2" else "passed"), verdict.detail
    if check_id == "C14":
        assert "not that the two resolutions agree" in verdict.detail


@pytest.mark.parametrize("check_id", ["C13", "C14"])
def test_a_target_without_a_quantity_has_nothing_to_compare(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == "not_applicable" and "no quantity" in verdict.detail


def test_c13_bites_a_parallel_run_that_writes_other_values(tmp_path):
    verdict = run_check("C13", quantity_toy_conformance_target(tmp_path, plugin=REORDERING_PARALLEL_PLUGIN))
    assert verdict.status == "failed"
    assert "'A': serial 0.0015, parallel 0.002" in verdict.detail


def test_c13_bites_a_parallel_form_that_is_the_serial_run(tmp_path):
    verdict = run_check("C13", quantity_toy_conformance_target(tmp_path, plugin=SERIAL_PARALLEL_PLUGIN))
    assert verdict.status == "failed"
    assert "planned the serial steps" in verdict.detail


def test_c13_bites_a_parallel_run_whose_solver_reports_one_rank(tmp_path):
    verdict = run_check("C13", quantity_toy_conformance_target(tmp_path, plugin=SINGLE_RANK_PLUGIN))
    assert verdict.status == "failed"
    assert "no step log matches" in verdict.detail and "with 2 ranks" in verdict.detail


def test_c13_bites_a_rank_count_the_declared_paths_do_not_match(tmp_path):
    target = quantity_toy_conformance_target(tmp_path)
    evidence = dataclasses.replace(target.quantity.rank_evidence, paths="split.*")
    target = dataclasses.replace(target, quantity=dataclasses.replace(target.quantity, rank_evidence=evidence))
    verdict = run_check("C13", target)
    assert verdict.status == "failed"
    assert "'split.*' matches 1 entries" in verdict.detail


def test_c14_bites_a_comparison_that_reads_nothing(tmp_path):
    """Only B is paired, and B is never reached on either side."""
    target = quantity_toy_conformance_target(tmp_path)
    only_b = {"B": target.quantity.at["B"]}
    target = dataclasses.replace(
        target, quantity=dataclasses.replace(target.quantity, pairs={"B": "B"}, at=only_b),
    )
    verdict = run_check("C14", target)
    assert verdict.status == "failed"
    assert "no pair is evaluated on both sides" in verdict.detail


def test_c1_and_c2_name_a_record_the_stack_does_not_serve(tmp_path):
    target = dataclasses.replace(toy_conformance_target(tmp_path), record="notARecord")
    for check_id in ("C1", "C2"):
        verdict = run_check(check_id, target)
        assert verdict.status == "failed" and "notARecord" in verdict.detail, (check_id, verdict.detail)


def test_c3_bites_a_validator_that_accepts_a_key_nobody_declared(tmp_path):
    target = dataclasses.replace(
        toy_conformance_target(tmp_path, plugin=ACCEPTING_PLUGIN), unknown_name="constant/mesh.json:nope",
    )
    verdict = run_check("C3", target)
    assert verdict.status == "failed" and "was accepted" in verdict.detail


def test_c5_bites_a_stack_whose_rule_refuses_the_native_case(tmp_path):
    verdict = run_check("C5", toy_conformance_target(tmp_path, plugin=BROKEN_RULE_PLUGIN))
    assert verdict.status == "failed" and "this toy's rule refuses every case" in verdict.detail


def test_a_refusal_printed_on_stdout_is_quoted_when_stderr_is_empty():
    from types import SimpleNamespace

    from omnidriver.conformance.checks import _output_tail

    refusal = '{"status": "failed", "error": "Execution environment preflight failed."}'
    assert "preflight failed" in _output_tail(SimpleNamespace(stdout=refusal, stderr=""))
    assert _output_tail(SimpleNamespace(stdout=refusal, stderr="Traceback")) == "Traceback"


def test_a_failed_step_diagnostic_in_the_workflow_state_is_quoted(tmp_path):
    import json

    from omnidriver.conformance.checks import _with_recorded_failure

    state = tmp_path / "workflow_state.json"
    state.write_text(json.dumps({"steps": [
        {"step_id": "mesh", "status": "completed", "diagnostics": []},
        {"step_id": "solve", "status": "failed", "diagnostics": [
            {"level": "error", "code": "solver_entry_missing", "message": "sealedHeartBoundary is required"},
            {"level": "warning", "code": "noise", "message": "ignored"},
        ]},
    ]}))

    problems = _with_recorded_failure(["missing artifacts ['record.solve.0']"], state, "the workflow state")

    assert problems[0] == "missing artifacts ['record.solve.0']"
    assert problems[1] == (
        "the workflow state recorded: step 'solve': solver_entry_missing: sealedHeartBoundary is required"
    )
    assert _with_recorded_failure([], tmp_path / "absent.json", "the workflow state") == []
