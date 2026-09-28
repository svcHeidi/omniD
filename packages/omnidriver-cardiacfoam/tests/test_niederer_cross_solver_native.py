"""An agent benchmarks openCARP against cardiacFOAM on the Niederer 2011 N-version slab end to end:
one ``sweep-run`` per solver, one comparison request, ``omnidriver compare``. Each side's points stay in
its own solver's frame; the pairing :data:`PROBES` and the constants were pre-registered before any run."""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from foamlib import FoamFile

from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT
from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import experiment_comparisons, load_point_reference
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from cardiacfoam_native import NIEDERER_2011_RELPATH, native_tutorials_root, niederer_sweep

#: Needs both native environments: the cardiacFOAM tree with OpenFOAM
#: sourced, and openCARP's tutorials tree with its binary. Each marker fails,
#: never skips, when its environment is missing.
pytestmark = [pytest.mark.native, pytest.mark.native_opencarp]

REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
_OPENCARP_NATIVE = Path(__file__).resolve().parents[2] / "omnidriver-opencarp" / "tests" / "opencarp_native.py"

# --- pre-registered: the same resolution, step and duration on both sides ---
# 200 ms is the native cartesianConvergence endTime at dx 0.5 mm, past the ~143 ms cardiacFOAM
# and ~126 ms openCARP need for their slowest probe.
CARDIACFOAM_DX_M = 0.0005          # the record's dx axis, metres
OPENCARP_DX_UM = 500.0             # the record's dx axis, µm: the same 0.5 mm
CARDIACFOAM_DELTA_T_S = 1e-5       # system/controlDict:deltaT, the native value
OPENCARP_DT_US = 10.0              # nversion.par:dt, µs: the same 0.01 ms
CARDIACFOAM_END_TIME_S = 0.2       # system/controlDict:endTime
OPENCARP_TEND_MS = 200.0           # nversion.par:tend, ms: the same 200 ms
TOLERANCE_MS = 5.0
TOLERANCE_RATIONALE = (
    "declared before either run was read; exploratory, not a benchmark acceptance claim. Two discretisations at "
    "dx 0.5 mm (openCARP P1 finite elements, linearly interpolated at the requested point; cardiacFOAM finite "
    "volumes, reported at the probe's own point under interpolationScheme cellPoint) are expected to differ. "
    "5 ms is the bound Tasks 6 and 7 used, and about half the 10.9 ms spread of P8 across the paper's codes at "
    "its finest resolution (37.8-48.7 ms, section 6)"
)
#: A point either solver leaves unactivated by 200 ms means the duration was
#: too short for that point; it must fail the report, not agree.
BOTH_NOT_REACHED = "fail"
#: With `interpolationScheme cellPoint`, cardiacFOAM reports each probe's configured location exactly.
CARDIACFOAM_MAX_OFFSET_M = 0.0
#: openCARP samples the nearest mesh node. At dx 500 µm every P1-P9 is a
#: node of the slab (a 41 x 15 x 7 grid), so any offset beyond rounding is
#: an orientation error. In the reference's unit, mm: 1 µm.
OPENCARP_MAX_OFFSET_MM = 0.001

#: The reference frame has its origin at P1, the stimulus corner, with a along the 20 mm fibre edge,
#: b along the 7 mm edge and c along the 3 mm edge, so x = a, y = c, z = 7 - b (mm) in cardiacFOAM's
#: frame; openCARP's frame is the reference frame in µm.
#: cardiacFOAM probe -> (its configured location in cardiacFOAM's frame, m;
#: the reference label; that label's reference coordinates, mm).
PROBES = {
    "0": ((0.0, 0.0, 0.007), "P1", (0, 0, 0)),
    "1": ((0.0, 0.0, 0.0), "P2", (0, 7, 0)),
    "2": ((0.019999, 0.0, 0.007), "P3", (20, 0, 0)),
    "3": ((0.019999, 0.0, 0.0), "P4", (20, 7, 0)),
    "4": ((0.0, 0.003, 0.007), "P5", (0, 0, 3)),
    "5": ((0.0, 0.003, 0.0), "P6", (0, 7, 3)),
    "6": ((0.019999, 0.003, 0.007), "P7", (20, 0, 3)),
    "7": ((0.019999, 0.003, 0.0), "P8", (20, 7, 3)),
    "8": ((0.01, 0.0015, 0.0035), "P9", (10, 3.5, 1.5)),
}
def _note(probe: str) -> str:
    at, label, reference_at = PROBES[probe]
    return (f"{label} {list(reference_at)} mm in the reference frame. openCARP: the reference frame itself, in um "
            f"(stimulus box at the origin, nversion.par stim[0].elec; F3 slab). cardiacFOAM probe {probe} at "
            f"{list(at)} m in its own frame (system/Niedererpoints), where x = a, y = c, z = 7 mm - b, because "
            "constant/electroProperties puts the stimulus box at the corner (0, 0, 7) mm")


def _opencarp_native() -> ModuleType:
    """Loaded from its file: a per-package run does not put openCARP's tests on ``sys.path``."""
    spec = importlib.util.spec_from_file_location("opencarp_native_for_cross_solver", _OPENCARP_NATIVE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module     # its dataclass resolves its own module while it executes
    spec.loader.exec_module(module)
    return module


def _artifact_id(output: Path, case, artifact_format: str) -> str:
    document = json.loads((output / case.run_document_path).read_text())
    (artifact,) = [a for a in document["expectedArtifacts"] if a["format"] == artifact_format]
    return artifact["artifact_id"]


def _slab_nodes(case_root: Path) -> list[tuple[float, float, float]]:
    """The openCARP mesh's nodes, µm: ``slab.pts`` holds a point count, then ``x y z`` per node."""
    count, *rows = (case_root / "slab.pts").read_text().split("\n")
    nodes = [tuple(float(v) for v in row.split()) for row in rows if row.strip()]
    assert len(nodes) == int(count)
    return nodes


def test_an_agent_compares_opencarp_with_cardiacfoam_at_p1_to_p9(tmp_path):
    # Drift gate: the pairing names the probes the native case configures, in its order.
    native = FoamFile(native_tutorials_root() / NIEDERER_2011_RELPATH / "system" / "Niedererpoints")["probeLocations"]
    assert [tuple(float(v) for v in xyz) for xyz in native] == [at for at, _, _ in PROBES.values()]
    reference = load_point_reference(REFERENCE)
    for at, label, reference_at in PROBES.values():
        assert reference.points[label].coordinates == tuple(float(v) for v in reference_at)

    opencarp_native = _opencarp_native()
    from omnidriver.opencarp.lat_reader import LAT_FORMAT   # openCARP is not installed in cardiacFOAM's CI job

    (tmp_path / "opencarp").mkdir()
    (tmp_path / "cardiacfoam").mkdir()
    oc_output = opencarp_native.niederer_sweep(tmp_path / "opencarp", dx_values=(OPENCARP_DX_UM,),
                                               tend=OPENCARP_TEND_MS, extra={"nversion.par:dt": OPENCARP_DT_US})
    cf_output = niederer_sweep(tmp_path / "cardiacfoam", dx_values=(CARDIACFOAM_DX_M,),
                               end_time=CARDIACFOAM_END_TIME_S,
                               extra={"system/controlDict:deltaT": CARDIACFOAM_DELTA_T_S})
    (oc_case,) = build_sweep_context(oc_output).cases
    (cf_case,) = build_sweep_context(cf_output).cases

    # Each side's points in its own solver's frame and unit, never converted.
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "reference": str(REFERENCE),
        "tolerance": {"kind": "absolute", "value": TOLERANCE_MS, "unit": "ms", "rationale": TOLERANCE_RATIONALE},
        "both_not_reached": BOTH_NOT_REACHED,
        "runs": {
            "opencarp": {"plugin": "opencarp", "sweep_output": str(oc_output), "case_id": oc_case.case_id,
                         "artifact_id": _artifact_id(oc_output, oc_case, LAT_FORMAT),
                         "points": {"unit": reference.length_unit,
                                    "at": {label: list(reference_at) for _, label, reference_at in PROBES.values()}},
                         "max_sampling_offset": OPENCARP_MAX_OFFSET_MM},
            "cardiacfoam": {"plugin": "cardiacfoam", "sweep_output": str(cf_output), "case_id": cf_case.case_id,
                            "artifact_id": _artifact_id(cf_output, cf_case, ACTIVATION_PROBES_FORMAT),
                            "points": {"unit": "m", "at": {probe: list(at) for probe, (at, _, _) in PROBES.items()}},
                            "max_sampling_offset": CARDIACFOAM_MAX_OFFSET_M},
        },
        "pairs": [{"reference_label": label, "left": {"run": "opencarp", "quantity": label},
                   "right": {"run": "cardiacfoam", "quantity": probe}, "note": _note(probe)}
                  for probe, (_, label, _) in PROBES.items()],
    }))
    report_path = tmp_path / "report.json"
    proc = subprocess.run([sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request),
                           "--report", str(report_path)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    report = json.loads(report_path.read_text())
    assert report["status"] in {"passed", "failed"}
    assert report["both_not_reached"] == BOTH_NOT_REACHED

    oc_nodes = _slab_nodes(oc_output / oc_case.case_root)
    by_label = {m["reference_label"]: m for m in report["metrics"]}
    assert set(by_label) == {label for _, label, _ in PROBES.values()}
    for k, (probe, (at, label, reference_at)) in enumerate(PROBES.items()):
        metric = by_label[label]
        assert metric["note"] == _note(probe)
        oc, cf = metric["left"], metric["right"]
        assert (oc["run"], oc["quantity"], cf["run"], cf["quantity"]) == ("opencarp", label, "cardiacfoam", probe)
        # The premise: 200 ms activates every point on both solvers.
        assert (oc["status"], cf["status"]) == ("evaluated", "evaluated"), (label, oc, cf)
        # openCARP: linearly interpolated at the requested point, a mesh node at dx 0.5 mm.
        assert (oc["declared_unit"], oc["unit"], oc["sampling_rule"], oc["sampled_at_unit"], oc["requested_at_unit"]) == (
            "ms", "ms", "linear", "um", "um")
        assert oc["requested_at"] == [1000.0 * v for v in reference_at]
        assert tuple(oc["sampled_at"]) in oc_nodes
        assert math.dist(oc["sampled_at"], oc["requested_at"]) == min(math.dist(n, oc["requested_at"]) for n in oc_nodes)
        # cardiacFOAM: at the probe's configured point exactly (interpolationScheme cellPoint).
        assert (cf["declared_unit"], cf["unit"], cf["sampling_rule"], cf["sampled_at_unit"], cf["requested_at_unit"]) == (
            "s", "ms", "point", "m", "m")
        assert cf["requested_at"] == list(at)
        assert cf["sampled_at"] == cf["requested_at"]
        assert metric["status"] in {"within_tolerance", "outside_tolerance", "sampled_off_point"}
    for side, max_offset in (("opencarp", OPENCARP_MAX_OFFSET_MM * 1000.0), ("cardiacfoam", CARDIACFOAM_MAX_OFFSET_M)):
        assert report["runs"][side]["max_sampling_offset"] == pytest.approx(max_offset)
    for output in (oc_output, cf_output):
        experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
        assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
        assert {case.comparison.status for case in experiment.cases} == {report["status"]}
