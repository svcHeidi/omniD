"""Comparison over agent-stated pairs: pre-registered, sentinel-aware,
bound to run evidence, refusing before it reads (spec 2026-09-26 §3, §4)."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from omnidriver.core import plugin_discovery
from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import QuantityComparisonError, experiment_comparisons, run_quantity_comparison
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from plugins.quantity_toy import (
    DIFFERENT_VERSION_QUANTITY_TOY_PLUGIN, GRID_FORMAT, NO_WHERE_READER_PLUGIN, QUANTITY_TOY_PLUGIN,
    RAISING_READER_PLUGIN, write_quantity_toy_case, write_toy_reference, write_toy_sweep,
)

TESTS_ROOT = Path(__file__).resolve().parents[1]
SAME = "a 0.0015 0 0 0.007\nb -1 0.02 0.003 0\n"
TOL = {"kind": "absolute", "value": 0.5, "unit": "ms", "rationale": "declared before reading, for this test"}


def _run(sweep, case_id, **extra):
    return {"plugin": QUANTITY_TOY_PLUGIN, "sweep_output": str(sweep), "case_id": case_id,
            "artifact_id": "record.solve.0", **extra}


def _request(tmp_path, runs, pairs, *, tolerance=TOL, reference=None, both_not_reached="agree"):
    reference = reference or write_toy_reference(tmp_path / "reference.json")
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"schema_version": 1, "reference": str(reference), "tolerance": tolerance,
                                "both_not_reached": both_not_reached, "runs": runs, "pairs": pairs}))
    return path


def _pair(label, left, right, lq=None, rq=None, **extra):
    return {"reference_label": label, "left": {"run": left, "quantity": lq or label.lower()},
            "right": {"run": right, "quantity": rq or label.lower()}, **extra}


def _two_runs(tmp_path, first=SAME, second=SAME, **sweep_kwargs):
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": first, "two": second}, **sweep_kwargs)
    return sweep, {"one": _run(sweep, "one"), "two": _run(sweep, "two")}


def test_equal_runs_pass_in_the_reference_unit_with_their_evidence(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "passed"
    (metric,) = report["metrics"]
    assert metric["status"] == "within_tolerance" and metric["difference"] == 0.0 and metric["bound"] == 0.5
    assert (metric["left"]["value"], metric["left"]["unit"], metric["left"]["declared_unit"]) == (pytest.approx(1.5), "ms", "s")
    assert (metric["left"]["sampled_at"], metric["left"]["sampled_at_unit"], metric["left"]["sampling_rule"]) == ([0.0, 0.0, 0.007], "m", "toy-row")
    assert metric["reference_coordinates"] == [0, 0, 0.007]
    assert {e["case_id"] for e in report["run_evidence"]} == {"one", "two"}
    assert report["request"]["digest"].startswith("sha256:")
    assert json.loads((tmp_path / "report.json").read_text()) == report


def test_a_difference_beyond_the_tolerance_fails(tmp_path):
    sweep, runs = _two_runs(tmp_path, second="a 0.0025 0 0 0.007\nb -1 0.02 0.003 0\n")
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "failed"
    assert report["metrics"][0]["status"] == "outside_tolerance"
    assert report["metrics"][0]["difference"] == pytest.approx(1.0)


def test_a_relative_tolerance_scales_with_the_larger_value(tmp_path):
    sweep, runs = _two_runs(tmp_path, second="a 0.00155 0 0 0.007\nb -1 0.02 0.003 0\n")
    tolerance = {"kind": "relative", "value": 0.05, "rationale": "five per cent, declared before reading"}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                     tmp_path / "report.json")
    assert report["metrics"][0]["status"] == "within_tolerance"
    assert report["metrics"][0]["bound"] == pytest.approx(0.05 * 1.55)


def test_sentinels_compare_as_statements_not_numbers(tmp_path):
    sweep, runs = _two_runs(tmp_path, second="a -1 0 0 0.007\nb -1 0.02 0.003 0\n")
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")]),
                                     tmp_path / "report.json")
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert by_label["B"]["status"] == "both_not_reached" and by_label["B"]["left"]["value"] is None
    assert by_label["A"]["status"] == "reached_on_one_side"
    assert report["status"] == "failed"


def test_both_not_reached_is_required_with_no_default(tmp_path):
    """I2/M1, controller review 2026-09-26: no default -- every request
    states its choice, or the schema refuses it before anything is read."""
    sweep, runs = _two_runs(tmp_path)
    reference = write_toy_reference(tmp_path / "reference.json")
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"schema_version": 1, "reference": str(reference), "tolerance": TOL,
                                "runs": runs, "pairs": [_pair("A", "one", "two")]}))  # no both_not_reached
    with pytest.raises(QuantityComparisonError, match="both_not_reached"):
        run_quantity_comparison(path, tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_both_not_reached_agree_does_not_fail_the_report(tmp_path):
    """SAME/SAME: 'a' is within_tolerance on both sides, 'b' is -1 on both
    (both_not_reached). With 'agree' that does not fail the report."""
    sweep, runs = _two_runs(tmp_path)
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")], both_not_reached="agree"),
        tmp_path / "report.json",
    )
    assert report["both_not_reached"] == "agree"
    assert report["status"] == "passed"
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert by_label["B"]["status"] == "both_not_reached"


def test_both_not_reached_fail_fails_the_report(tmp_path):
    """I2, controller review 2026-09-26: the pre-registered alternative --
    'fail' turns a both_not_reached pair into a failure, exactly like any
    other failing status."""
    sweep, runs = _two_runs(tmp_path)
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")], both_not_reached="fail"),
        tmp_path / "report.json",
    )
    assert report["both_not_reached"] == "fail"
    assert report["status"] == "failed"


def test_status_is_unavailable_when_nothing_is_compared_numerically(tmp_path):
    """I2/M1: a report full of both_not_reached pairs must never claim
    'passed' -- it says why in status_reason."""
    sweep, runs = _two_runs(tmp_path)
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("B", "one", "two")], both_not_reached="agree"), tmp_path / "report.json",
    )
    assert report["status"] == "unavailable"
    assert "within_tolerance" in report["status_reason"]


def test_a_missing_artifact_is_not_evaluated_with_its_reason(tmp_path):
    sweep, runs = _two_runs(tmp_path, second=None)
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "unavailable"
    right = report["metrics"][0]["right"]
    assert right["status"] == "not_evaluated" and "missing" in right["reason"]


def test_a_report_is_written_once(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    request = _request(tmp_path, runs, [_pair("A", "one", "two")])
    run_quantity_comparison(request, tmp_path / "report.json")
    with pytest.raises(QuantityComparisonError, match="already exists"):
        run_quantity_comparison(request, tmp_path / "report.json")


@pytest.mark.parametrize(("edit", "match"), [
    (lambda runs, pairs: pairs.append(_pair("Q", "one", "two", "a", "a")), "'Q'.*the toy never says"),
    (lambda runs, pairs: pairs.append(_pair("Z", "one", "two", "a", "a")), "'Z'"),
    (lambda runs, pairs: pairs.append(_pair("A", "one", "three")), "'three'"),
    (lambda runs, pairs: pairs.append(_pair("A", "one", "one")), "itself"),
    (lambda runs, pairs: runs["one"].update(case_id="nine"), "'nine'"),
    (lambda runs, pairs: runs["one"].update(artifact_id="record.solve.7"), "record.solve.7"),
    # I3, controller review 2026-09-26: a self-sampling reader (takes_points
    # is false) now *accepts* 'points' as expected locations, so this no
    # longer fails with "takes no points" -- it fails because 'points' is
    # given without the now-required 'max_sampling_offset' (I2/M1).
    (lambda runs, pairs: runs["one"].update(points={"unit": "m", "at": {"a": [0, 0, 0]}}), "max_sampling_offset"),
    (lambda runs, pairs: runs.update(spare=dict(runs["one"])), "'spare'.*no pair"),
])
def test_a_malformed_request_is_refused_before_anything_is_read(tmp_path, edit, match):
    sweep, runs = _two_runs(tmp_path)
    pairs = [_pair("A", "one", "two")]
    edit(runs, pairs)
    with pytest.raises(QuantityComparisonError, match=match):
        run_quantity_comparison(_request(tmp_path, runs, pairs), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_tolerance_in_the_wrong_dimension_is_refused(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "wrong on purpose"}
    with pytest.raises(QuantityComparisonError, match="'mm'"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                tmp_path / "report.json")


def test_an_absolute_tolerance_without_a_unit_is_refused_by_the_schema(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    tolerance = {"kind": "absolute", "value": 1.0, "rationale": "no unit given"}
    with pytest.raises(QuantityComparisonError, match="not a comparison request"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_relative_tolerance_with_a_unit_is_refused_by_the_schema(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    tolerance = {"kind": "relative", "value": 0.05, "unit": "ms", "rationale": "relative tolerances carry no unit"}
    with pytest.raises(QuantityComparisonError, match="not a comparison request"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_pair_may_override_the_default_tolerance(tmp_path):
    sweep, runs = _two_runs(tmp_path, second="a 0.0025 0 0 0.007\nb -1 0.02 0.003 0\n")
    loose = {"kind": "absolute", "value": 2.0, "unit": "ms", "rationale": "this pair alone tolerates more"}
    pair = _pair("A", "one", "two", tolerance=loose)
    report = run_quantity_comparison(_request(tmp_path, runs, [pair]), tmp_path / "report.json")
    assert report["metrics"][0]["status"] == "within_tolerance" and report["metrics"][0]["bound"] == 2.0


def test_a_pair_tolerance_in_the_wrong_dimension_is_refused(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    bad = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "wrong on purpose, per-pair"}
    pair = _pair("A", "one", "two", tolerance=bad)
    with pytest.raises(QuantityComparisonError, match="pair 0.*'mm'"):
        run_quantity_comparison(_request(tmp_path, runs, [pair]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_reader_unit_that_cannot_become_the_reference_unit_is_refused(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    reference = write_toy_reference(tmp_path / "reference.json", quantity_unit="mm")
    tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "length reference, time reader"}
    with pytest.raises(QuantityComparisonError, match="run 'one'.*'s'.*'mm'"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance,
                                         reference=reference), tmp_path / "report.json")


def test_a_run_planned_with_another_stack_is_refused(tmp_path):
    """A stack that really differs (here, a declared plugin_version a real
    version bump would change) is refused. Rewritten per controller review
    B1 (2026-09-26): two distinct classes sharing MinimalTestPlugin's
    hardcoded plugin_id are NOT a different stack by the shared
    `stack_identity_mismatch` check (only `source`, deliberately excluded,
    told them apart) -- see `test_the_same_plugin_loaded_by_import_path_and_by_name_is_accepted`."""
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, plugin=QUANTITY_TOY_PLUGIN)
    runs = {"one": _run(sweep, "one", plugin=DIFFERENT_VERSION_QUANTITY_TOY_PLUGIN), "two": _run(sweep, "two")}
    with pytest.raises(QuantityComparisonError, match="was planned with"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")


class _FakeQuantityToyEntryPoint:
    """A discovered (no-colon) form of QUANTITY_TOY_PLUGIN, so a run can be
    re-loaded by name instead of by its trusted import path."""

    name = "quantity-toy"
    value = "plugins.quantity_toy:QuantityToyPlugin"
    dist = type("D", (), {"name": "toy-dist", "version": "1"})()

    def load(self):
        from plugins.quantity_toy import QuantityToyPlugin

        return QuantityToyPlugin


def test_the_same_plugin_loaded_by_import_path_and_by_name_is_accepted(tmp_path, monkeypatch):
    """B1: the stack comparison is insensitive to `source` on purpose --
    reloading the identical provider through a different install/import
    path is not a "different stack" refusal."""
    monkeypatch.setattr(plugin_discovery, "_entry_points", lambda: (_FakeQuantityToyEntryPoint(),))
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, plugin=QUANTITY_TOY_PLUGIN)
    runs = {"one": _run(sweep, "one", plugin="quantity-toy"), "two": _run(sweep, "two")}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "passed"


def test_points_are_converted_to_the_reader_unit_and_an_off_point_sample_fails(tmp_path):
    grid = "0 0 0 1.0\n1 0 0 2.0\n"
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": grid, "two": grid}, artifact_format=GRID_FORMAT)
    points = {"unit": "m", "at": {"a": [0.0009, 0, 0]}}
    # "one" is given a generous offset (I2/M1: 'points' now always requires
    # 'max_sampling_offset', so it can no longer be left unchecked) that its
    # own 0.1 mm offset never exceeds; only "two"'s tight 0.00005 m bound
    # catches the same reader's same offset, keeping the asymmetry this test
    # is about.
    runs = {"one": _run(sweep, "one", points=points, max_sampling_offset=1.0),
            "two": _run(sweep, "two", points=points, max_sampling_offset=0.00005)}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    (metric,) = report["metrics"]
    assert metric["left"]["requested_at"] == [pytest.approx(0.9), 0.0, 0.0]
    assert metric["left"]["sampled_at"] == [1.0, 0.0, 0.0] and metric["left"]["sampled_at_unit"] == "mm"
    assert metric["right"]["sampling_offset"] == pytest.approx(0.1)
    assert metric["status"] == "sampled_off_point" and report["status"] == "failed"
    # M7, controller review 2026-09-26: every location number carries its
    # unit -- these are all in the reader's coordinate_unit ("mm"), not the
    # request's own ("m").
    assert metric["left"]["requested_at_unit"] == "mm"
    assert metric["right"]["sampling_offset_unit"] == "mm"
    assert report["runs"]["two"]["max_sampling_offset_unit"] == "mm"


def test_a_points_taking_reader_without_points_is_refused(tmp_path):
    grid = "0 0 0 1.0\n1 0 0 2.0\n"
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": grid, "two": grid}, artifact_format=GRID_FORMAT)
    runs = {"one": _run(sweep, "one"), "two": _run(sweep, "two")}
    with pytest.raises(QuantityComparisonError, match="samples at supplied points"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_points_taking_reader_with_a_mismatched_label_set_is_refused(tmp_path):
    grid = "0 0 0 1.0\n1 0 0 2.0\n"
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": grid, "two": grid}, artifact_format=GRID_FORMAT)
    points = {"unit": "m", "at": {"not-a": [0, 0, 0]}}
    runs = {"one": _run(sweep, "one", points=points), "two": _run(sweep, "two", points=points)}
    with pytest.raises(QuantityComparisonError, match="points are given for"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_points_for_a_stack_with_no_reader_are_refused_before_any_read(tmp_path):
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, artifact_format="toy_unreadable_format")
    points = {"unit": "m", "at": {"a": [0, 0, 0]}}
    runs = {"one": _run(sweep, "one", points=points), "two": _run(sweep, "two")}
    with pytest.raises(QuantityComparisonError, match="no reader"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_max_sampling_offset_for_a_stack_with_no_reader_is_also_refused(tmp_path):
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, artifact_format="toy_unreadable_format")
    runs = {"one": _run(sweep, "one", max_sampling_offset=0.001), "two": _run(sweep, "two")}
    with pytest.raises(QuantityComparisonError, match="no reader"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_expected_points_for_a_self_sampling_reader_pass_within_the_offset(tmp_path):
    """I3, controller review 2026-09-26: a reader that samples where it
    chooses (ToyRowReader, takes_points is false) may still be given
    'points' -- as the agent's *expected* location, checked against
    ToyRowReader's own sampled_at, never handed to the reader."""
    sweep, runs = _two_runs(tmp_path)
    points = {"unit": "m", "at": {"a": [0, 0, 0.007], "b": [0.02, 0.003, 0]}}
    runs["one"].update(points=points, max_sampling_offset=0.001)
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")], both_not_reached="agree"),
        tmp_path / "report.json",
    )
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert by_label["A"]["left"]["requested_at"] == [0, 0, 0.007]
    assert by_label["A"]["left"]["requested_at_unit"] == "m"
    assert by_label["A"]["left"]["sampling_offset"] == 0.0
    assert by_label["A"]["status"] == "within_tolerance"


def test_expected_points_for_a_self_sampling_reader_catch_a_mispairing(tmp_path):
    """I3: a far expected location becomes sampled_off_point, exactly as
    for a points-taking reader -- a wrong pairing is visible, not silent."""
    sweep, runs = _two_runs(tmp_path)
    points = {"unit": "m", "at": {"a": [5, 5, 5], "b": [0.02, 0.003, 0]}}
    runs["one"].update(points=points, max_sampling_offset=0.001)
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")], both_not_reached="agree"),
        tmp_path / "report.json",
    )
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert by_label["A"]["left"]["sampling_offset"] == pytest.approx(math.dist((5, 5, 5), (0, 0, 0.007)))
    assert by_label["A"]["status"] == "sampled_off_point"
    assert report["status"] == "failed"


def test_points_for_a_self_sampling_reader_without_max_sampling_offset_is_refused(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    runs["one"]["points"] = {"unit": "m", "at": {"a": [0, 0, 0.007], "b": [0.02, 0.003, 0]}}
    with pytest.raises(QuantityComparisonError, match="max_sampling_offset"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")]),
                                tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_self_sampling_reader_with_no_location_is_a_named_gap_when_points_are_given(tmp_path):
    """I3: NoWhereReaderPlugin's reader never reports sampled_at (like I1,
    but for a self-sampling reader) -- with expected points given, that is
    a named not_evaluated gap, not a silently unchecked pass."""
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, plugin=NO_WHERE_READER_PLUGIN)
    points = {"unit": "m", "at": {"a": [0, 0, 0.007]}}
    runs = {"one": _run(sweep, "one", plugin=NO_WHERE_READER_PLUGIN, points=points, max_sampling_offset=0.001),
            "two": _run(sweep, "two", plugin=NO_WHERE_READER_PLUGIN, points=points, max_sampling_offset=0.001)}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], both_not_reached="agree"),
                                     tmp_path / "report.json")
    left = report["metrics"][0]["left"]
    assert left["status"] == "not_evaluated"
    assert "sampled_at" in left["reason"]


def test_a_pair_naming_two_different_runs_that_resolve_to_the_same_place_is_refused(tmp_path):
    """N1 (controller review 2026-09-26): the refusal is about what a pair's
    two sides actually resolve to, not whether they spell the same run
    name."""
    sweep, runs = _two_runs(tmp_path)
    runs["one_alias"] = dict(runs["one"])
    with pytest.raises(QuantityComparisonError, match="itself"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "one_alias")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_two_run_names_for_the_same_case_are_not_double_counted_as_evidence(tmp_path):
    """B2 (controller review 2026-09-26): two run names that resolve to one
    case must not produce two identical run_evidence entries, or
    `experiments._association_status`'s "exactly one match" rule would see
    two and call it unverified."""
    sweep, runs = _two_runs(tmp_path)
    runs["one_again"] = dict(runs["one"])
    report_path = tmp_path / "report.json"
    report = run_quantity_comparison(
        _request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one_again", "two")]), report_path,
    )
    assert report["status"] == "passed"
    assert len(report["run_evidence"]) == 2  # "one"/"one_again" -> one case; "two" is a distinct case
    experiment = inspect_sweep_experiment(sweep, comparisons=experiment_comparisons(report_path, sweep_output=sweep))
    assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}


def test_a_case_that_did_not_complete_is_not_evaluated_with_its_status(tmp_path):
    sweep, runs = _two_runs(tmp_path, status="failed")
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "unavailable"
    left = report["metrics"][0]["left"]
    assert left["status"] == "not_evaluated" and "'failed'" in left["reason"]


def test_relative_reference_and_sweep_output_resolve_against_the_requests_directory(tmp_path):
    write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME})
    write_toy_reference(tmp_path / "reference.json")
    request_dir = tmp_path / "requests"
    request_dir.mkdir()
    request = request_dir / "request.json"
    relative_runs = {
        "one": {"plugin": QUANTITY_TOY_PLUGIN, "sweep_output": "../sweep", "case_id": "one",
                "artifact_id": "record.solve.0"},
        "two": {"plugin": QUANTITY_TOY_PLUGIN, "sweep_output": "../sweep", "case_id": "two",
                "artifact_id": "record.solve.0"},
    }
    request.write_text(json.dumps({"schema_version": 1, "reference": "../reference.json", "tolerance": TOL,
                                   "both_not_reached": "agree",
                                   "runs": relative_runs, "pairs": [_pair("A", "one", "two")]}))
    report = run_quantity_comparison(request, request_dir / "report.json")
    assert report["status"] == "passed"


def test_a_reader_exception_other_than_valueerror_becomes_a_named_gap(tmp_path):
    """N3 (controller review 2026-09-26): a report is always written, even
    when a reader raises something core never anticipated."""
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME}, plugin=RAISING_READER_PLUGIN)
    runs = {"one": _run(sweep, "one", plugin=RAISING_READER_PLUGIN),
            "two": _run(sweep, "two", plugin=RAISING_READER_PLUGIN)}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert report["status"] == "unavailable"
    left = report["metrics"][0]["left"]
    assert left["status"] == "not_evaluated"
    assert "OSError" in left["reason"] and "disk fell over" in left["reason"]


def test_a_hard_link_failure_is_a_named_refusal_not_a_traceback(tmp_path, monkeypatch):
    """N3 (controller review 2026-09-26): a filesystem without hard-link
    support refuses by name and never overwrites -- it is not a traceback."""
    from omnidriver.core.quantities import comparison as comparison_module

    def _no_hardlinks(*_args, **_kwargs):
        raise OSError("no hard link support on this filesystem")

    monkeypatch.setattr(comparison_module.os, "link", _no_hardlinks)
    sweep, runs = _two_runs(tmp_path)
    report_path = tmp_path / "report.json"
    with pytest.raises(QuantityComparisonError, match="hard-linking"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), report_path)
    assert not report_path.exists()


def test_a_report_directory_creation_failure_is_a_named_refusal(tmp_path, monkeypatch):
    """M10, controller review 2026-09-26: `_write_once`'s `mkdir` used to be
    a bare `OSError` traceback."""
    from omnidriver.core.quantities import comparison as comparison_module

    def _no_mkdir(self, *args, **kwargs):
        raise OSError("no permission to create directories here")

    sweep, runs = _two_runs(tmp_path)
    request = _request(tmp_path, runs, [_pair("A", "one", "two")])
    monkeypatch.setattr(comparison_module.Path, "mkdir", _no_mkdir)
    with pytest.raises(QuantityComparisonError, match="cannot create the report directory"):
        run_quantity_comparison(request, tmp_path / "reports" / "report.json")


def test_a_report_write_failure_is_a_named_refusal(tmp_path, monkeypatch):
    """M10: `_write_once`'s `write_text` used to be a bare `OSError`
    traceback."""
    from omnidriver.core.quantities import comparison as comparison_module

    sweep, runs = _two_runs(tmp_path)
    request = _request(tmp_path, runs, [_pair("A", "one", "two")])

    def _no_write(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(comparison_module.Path, "write_text", _no_write)
    with pytest.raises(QuantityComparisonError, match="cannot write report"):
        run_quantity_comparison(request, tmp_path / "report.json")


def test_a_malformed_expected_artifact_entry_is_refused_by_name(tmp_path):
    """M10: `data_artifact_from_json` can raise KeyError/ValueError for a
    malformed `expectedArtifacts` entry; that must be a named
    QuantityComparisonError, not a traceback."""
    sweep, runs = _two_runs(tmp_path)
    document_path = sweep / "cases" / "one" / "run_document.json"
    document = json.loads(document_path.read_text())
    document["expectedArtifacts"] = [{"artifact_id": "record.solve.0"}]  # no path_pattern/format
    document_path.write_text(json.dumps(document))
    with pytest.raises(QuantityComparisonError, match="malformed"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_the_report_is_written_read_only(tmp_path):
    """M6, controller review 2026-09-26: pre-registration is not just
    asserted -- the written report is chmod'd read-only."""
    import stat

    sweep, runs = _two_runs(tmp_path)
    report_path = tmp_path / "report.json"
    run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), report_path)
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o444


def test_the_n1_guard_is_not_bypassed_by_an_unnormalised_path(tmp_path):
    """M2, controller review 2026-09-26: `_location` used to compare a
    resolved-but-not-normalised path, so 'sweep' and 'sweep/../sweep' -- the
    same place, spelled differently -- were not recognised as one run, and
    N1's self-comparison guard was bypassed."""
    sweep, runs = _two_runs(tmp_path)
    runs["one_unnormalised"] = {**runs["one"], "sweep_output": str(sweep) + "/../" + sweep.name}
    with pytest.raises(QuantityComparisonError, match="itself"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "one_unnormalised")]), tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_a_refused_request_never_calls_the_reader(tmp_path, monkeypatch):
    """A spy reader proves refusal happens before any read (N5, controller
    review 2026-09-26): a bad-tolerance request is refused before any run
    is even resolved, so patching the reader to explode changes nothing."""
    from plugins.quantity_toy import ToyRowReader

    def _spy(self, case_root, artifact, request):
        raise AssertionError("reader.read must not be called for a refused request")

    monkeypatch.setattr(ToyRowReader, "read", _spy)
    sweep, runs = _two_runs(tmp_path)
    tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "wrong on purpose"}
    with pytest.raises(QuantityComparisonError, match="'mm'"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                tmp_path / "report.json")


def test_the_report_attaches_to_each_run_in_the_experiment_envelope(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    report_path = tmp_path / "report.json"
    run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), report_path)
    experiment = inspect_sweep_experiment(sweep, comparisons=experiment_comparisons(report_path, sweep_output=sweep))
    assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
    assert {case.comparison.status for case in experiment.cases} == {"passed"}
    assert {case.comparison.checker_id for case in experiment.cases} == {"omnidriver.quantities"}


def test_an_agent_compares_two_real_runs_through_the_cli(tmp_path):
    """End to end: sweep-run the toy record, then `omnidriver compare`."""
    cases_root = tmp_path / "native"
    write_quantity_toy_case(cases_root, SAME)
    spec = tmp_path / "sweep.json"
    spec.write_text(json.dumps({"base": {"entry": "toyQuantities", "cases_root": str(cases_root)},
                                "sweep": {"mode": "cross_product", "independent": {"number_cells": [2, 3]}}}))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(TESTS_ROOT), os.environ.get("PYTHONPATH", "")])}
    out = tmp_path / "sweep"
    swept = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", QUANTITY_TOY_PLUGIN, "--spec", str(spec),
         "--output-dir", str(out), "--scratch-dir", str(tmp_path / "scratch")],
        capture_output=True, text=True, env=env,
    )
    assert swept.returncode == 0, swept.stdout[-2000:] + swept.stderr[-2000:]
    first, second = sorted(case.case_id for case in build_sweep_context(out).cases)
    request = _request(tmp_path, {"two": _run(out, first), "three": _run(out, second)},
                       [_pair("A", "two", "three"), _pair("B", "two", "three")])
    report_path = tmp_path / "report.json"
    command = [sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request), "--report", str(report_path)]
    compared = subprocess.run(command, capture_output=True, text=True, env=env)
    assert compared.returncode == 0, compared.stdout[-2000:] + compared.stderr[-2000:]
    report = json.loads(report_path.read_text())
    assert report["status"] == "passed"
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert by_label["A"]["left"]["value"] == pytest.approx(1.5) and by_label["B"]["status"] == "both_not_reached"
    experiment = inspect_sweep_experiment(out, comparisons=experiment_comparisons(report_path, sweep_output=out))
    assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
    again = subprocess.run(command, capture_output=True, text=True, env=env)
    assert again.returncode == 1 and "already exists" in json.loads(again.stdout)["error"]
