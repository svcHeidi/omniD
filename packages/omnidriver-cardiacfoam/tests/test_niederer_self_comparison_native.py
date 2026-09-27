"""An agent compares cardiacFOAM with itself at two resolutions, end to end,
exactly as it would: sweep-run, read the run documents, write a request from
the reference, `omnidriver compare`, attach the report to the experiment
(spec 2026-09-26 §4; topic B Task 7). Cross-solver is Task 8.

The agent's pairing and expected locations, stated here, not derived by
core: cardiacFOAM probe ``k`` is the reference's ``P<k+1>`` (the owner's
appendix, via the reference's own ``niederer2011-owner-appendix`` source),
and each probe's expected location is its configured one, read from the
native ``system/Niedererpoints`` in cardiacFOAM's own frame, metres -- no
frame conversion. **Updated 2026-09-27 (native `interpolationScheme
cellPoint`, e9439c4f):** the reader now reports each probe's own configured
location exactly (offset 0, ``sampling_rule == "point"``), not the
containing cell's centre -- the pre-registered ``max_sampling_offset`` is 0.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from foamlib import FoamFile

from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT
from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import experiment_comparisons
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from cardiacfoam_native import NIEDERER_2011_RELPATH, native_tutorials_root, niederer_sweep

pytestmark = pytest.mark.native

REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
DX_VALUES = (0.0005, 0.001)
END_TIME = 0.1
TOLERANCE_MS = 5.0
#: Q7 (a real run of each resolution to 0.2 s, before this test was written):
#: by 0.1 s, P1 and P3 (probes 0 and 2) have activated at both resolutions;
#: P5, P7 and P9 (probes 4, 6, 8) at dx 0.5 mm only; P2, P4, P6 and P8 at
#: neither (dx 0.5 mm reaches them after 0.13 s; dx 1 mm not by 0.2 s).
BOTH_REACHED = {"P1", "P3"}
ONE_SIDE = {"P5", "P7", "P9"}


def _artifact_id(output: Path, case) -> str:
    document = json.loads((output / case.run_document_path).read_text())
    (artifact,) = [a for a in document["expectedArtifacts"] if a["format"] == ACTIVATION_PROBES_FORMAT]
    return artifact["artifact_id"]


def test_an_agent_compares_dx_1_mm_with_dx_0_5_mm_at_the_probes(tmp_path):
    output = niederer_sweep(tmp_path, dx_values=DX_VALUES, end_time=END_TIME)
    cases = {case.resolved_axis_values["dx"]: case for case in build_sweep_context(output).cases}
    locations = FoamFile(native_tutorials_root() / NIEDERER_2011_RELPATH / "system" / "Niedererpoints")["probeLocations"]
    expected = {str(k): [float(v) for v in xyz] for k, xyz in enumerate(locations)}
    labels = {str(k): f"P{k + 1}" for k in range(len(expected))}

    def run(dx: float) -> dict:
        case = cases[dx]
        return {"plugin": "cardiacfoam", "sweep_output": str(output), "case_id": case.case_id,
                "artifact_id": _artifact_id(output, case), "points": {"unit": "m", "at": expected},
                "max_sampling_offset": 0.0}

    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "reference": str(REFERENCE),
        "tolerance": {"kind": "absolute", "value": TOLERANCE_MS, "unit": "ms",
                      "rationale": "declared before either run was read; exploratory, a self-comparison across "
                                   "resolution, not a benchmark acceptance claim"},
        # Pre-registered: a probe neither resolution reaches by END_TIME says
        # nothing about agreement, but must not fail the report by itself.
        "both_not_reached": "agree",
        "runs": {"dx1": run(0.001), "dx05": run(0.0005)},
        "pairs": [{"reference_label": labels[k], "left": {"run": "dx1", "quantity": k},
                   "right": {"run": "dx05", "quantity": k},
                   "note": f"cardiacFOAM probe {k} is {labels[k]} (owner appendix pairing)"} for k in expected],
    }))
    report_path = tmp_path / "report.json"
    proc = subprocess.run([sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request),
                           "--report", str(report_path)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    report = json.loads(report_path.read_text())
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert set(by_label) == set(labels.values())
    for label, metric in by_label.items():
        for side, dx in (("left", 0.001), ("right", 0.0005)):
            shown = metric[side]
            assert (shown["unit"], shown["declared_unit"], shown["sampling_rule"], shown["sampled_at_unit"],
                    shown["requested_at_unit"]) == ("ms", "s", "point", "m", "m")
            assert shown["sampling_offset"] == 0
            assert shown["sampled_at"] == shown["requested_at"]
            reached = label in BOTH_REACHED or (label in ONE_SIDE and side == "right")
            assert shown["status"] == ("evaluated" if reached else "not_reached"), (label, side, shown)
        if label in BOTH_REACHED:
            difference = abs(metric["left"]["value"] - metric["right"]["value"])
            assert metric["status"] == ("within_tolerance" if difference <= TOLERANCE_MS else "outside_tolerance")
        else:
            assert metric["status"] == ("reached_on_one_side" if label in ONE_SIDE else "both_not_reached")
    assert by_label["P1"]["status"] == "within_tolerance"
    assert report["status"] == "failed"    # P5, P7 and P9 are reached on one side only
    experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
    assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
    assert {case.comparison.status for case in experiment.cases} == {report["status"]}
