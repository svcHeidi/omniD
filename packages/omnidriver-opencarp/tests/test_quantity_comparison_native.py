"""An agent compares two openCARP resolutions at the paper's points, end to
end, exactly as it would: sweep-run, read the run documents, write a
request from the reference, `omnidriver compare`, attach the report to the
experiment (spec 2026-09-26 §4)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import experiment_comparisons, load_point_reference
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from omnidriver.opencarp.lat_reader import LAT_FORMAT
from opencarp_native import niederer_sweep

pytestmark = pytest.mark.native_opencarp

REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
TOLERANCE_MS = 5.0


def _lat_artifact_id(output: Path, case) -> str:
    document = json.loads((output / case.run_document_path).read_text())
    (artifact,) = [a for a in document["expectedArtifacts"] if a["format"] == LAT_FORMAT]
    return artifact["artifact_id"]


def test_an_agent_compares_dx_500_with_dx_250_at_the_paper_points(tmp_path):
    output = niederer_sweep(tmp_path, dx_values=(500.0, 250.0), tend=150.0)
    cases = {case.resolved_axis_values["dx"]: case for case in build_sweep_context(output).cases}
    reference = load_point_reference(REFERENCE)
    # The agent's orientation step: openCARP's slab is the reference frame
    # (F3: 0-20000 x 0-7000 x 0-3000 um, stimulus cube at the origin, fibres
    # along x), so the reference coordinates are written unchanged, in the
    # reference's own unit; core converts mm to the reader's um.
    labels = [label for label, point in reference.points.items() if point.coordinates is not None]
    points = {"unit": reference.length_unit, "at": {label: list(reference.points[label].coordinates) for label in labels}}

    def run(dx: float) -> dict:
        case = cases[dx]
        return {"plugin": "opencarp", "sweep_output": str(output), "case_id": case.case_id,
                "artifact_id": _lat_artifact_id(output, case), "points": points, "max_sampling_offset": 0.001}

    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "reference": str(REFERENCE),
        "tolerance": {"kind": "absolute", "value": TOLERANCE_MS, "unit": "ms",
                      "rationale": "declared before either run was read; exploratory, not a benchmark acceptance claim"},
        "runs": {"dx500": run(500.0), "dx250": run(250.0)},
        "pairs": [{"reference_label": label, "left": {"run": "dx500", "quantity": label},
                   "right": {"run": "dx250", "quantity": label}} for label in labels],
    }))
    report_path = tmp_path / "report.json"
    proc = subprocess.run([sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request),
                           "--report", str(report_path)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    report = json.loads(report_path.read_text())
    assert report["status"] in {"passed", "failed"}          # every pair was evaluated
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert set(by_label) == set(labels)
    for metric in by_label.values():
        for side in (metric["left"], metric["right"]):
            assert (side["status"], side["unit"], side["declared_unit"], side["sampling_rule"], side["sampled_at_unit"]) == (
                "evaluated", "ms", "ms", "node", "um")
            assert side["sampling_offset"] == 0.0 and side["source_artifact"] == "out/init_acts_vm_act-thresh.dat"
        difference = abs(metric["left"]["value"] - metric["right"]["value"])
        assert metric["difference"] == pytest.approx(difference)
        assert metric["status"] == ("within_tolerance" if difference <= TOLERANCE_MS else "outside_tolerance")
    for side in ("left", "right"):
        assert by_label["P1"][side]["value"] < by_label["P9"][side]["value"] < by_label["P8"][side]["value"]
    assert by_label["P8"]["left"]["value"] == pytest.approx(126.45, abs=5e-3)   # G4, dx 500
    experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
    assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
    assert {case.comparison.status for case in experiment.cases} == {report["status"]}
