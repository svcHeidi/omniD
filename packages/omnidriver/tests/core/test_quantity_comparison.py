"""Comparison over agent-stated pairs: pre-registered, sentinel-aware,
bound to run evidence, refusing before it reads (spec 2026-09-26 §3, §4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import QuantityComparisonError, experiment_comparisons, run_quantity_comparison
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from plugins.quantity_toy import (
    GRID_FORMAT, QUANTITY_TOY_PLUGIN, write_quantity_toy_case, write_toy_reference, write_toy_sweep,
)

TESTS_ROOT = Path(__file__).resolve().parents[1]
SAME = "a 0.0015 0 0 0.007\nb -1 0.02 0.003 0\n"
TOL = {"kind": "absolute", "value": 0.5, "unit": "ms", "rationale": "declared before reading, for this test"}


def _run(sweep, case_id, **extra):
    return {"plugin": QUANTITY_TOY_PLUGIN, "sweep_output": str(sweep), "case_id": case_id,
            "artifact_id": "record.solve.0", **extra}


def _request(tmp_path, runs, pairs, *, tolerance=TOL, reference=None):
    reference = reference or write_toy_reference(tmp_path / "reference.json")
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"schema_version": 1, "reference": str(reference), "tolerance": tolerance,
                                "runs": runs, "pairs": pairs}))
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
    (lambda runs, pairs: runs["one"].update(points={"unit": "m", "at": {"a": [0, 0, 0]}}), "takes no points"),
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


def test_a_reader_unit_that_cannot_become_the_reference_unit_is_refused(tmp_path):
    sweep, runs = _two_runs(tmp_path)
    reference = write_toy_reference(tmp_path / "reference.json", quantity_unit="mm")
    tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "length reference, time reader"}
    with pytest.raises(QuantityComparisonError, match="run 'one'.*'s'.*'mm'"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance,
                                         reference=reference), tmp_path / "report.json")


def test_a_run_planned_with_another_stack_is_refused(tmp_path):
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME},
                            plugin="plugins.e2e_record_plugin:E2ERecordPlugin")
    runs = {"one": _run(sweep, "one"), "two": _run(sweep, "two")}
    with pytest.raises(QuantityComparisonError, match="was planned with"):
        run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")


def test_points_are_converted_to_the_reader_unit_and_an_off_point_sample_fails(tmp_path):
    grid = "0 0 0 1.0\n1 0 0 2.0\n"
    sweep = write_toy_sweep(tmp_path / "sweep", {"one": grid, "two": grid}, artifact_format=GRID_FORMAT)
    points = {"unit": "m", "at": {"a": [0.0009, 0, 0]}}
    runs = {"one": _run(sweep, "one", points=points), "two": _run(sweep, "two", points=points, max_sampling_offset=0.00005)}
    report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
    (metric,) = report["metrics"]
    assert metric["left"]["requested_at"] == [pytest.approx(0.9), 0.0, 0.0]
    assert metric["left"]["sampled_at"] == [1.0, 0.0, 0.0] and metric["left"]["sampled_at_unit"] == "mm"
    assert metric["right"]["sampling_offset"] == pytest.approx(0.1)
    assert metric["status"] == "sampled_off_point" and report["status"] == "failed"


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
