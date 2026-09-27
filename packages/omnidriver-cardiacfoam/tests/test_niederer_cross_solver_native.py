"""An agent benchmarks openCARP against cardiacFOAM on the Niederer 2011
N-version slab, end to end, exactly as it would: one ``sweep-run`` per
solver, read each run document, write one comparison request from the
reference, ``omnidriver compare``, attach the report to both experiments
(spec 2026-09-26 §4; topic B Task 8, the benchmarker's step 3).

**The agent's orientation, read from the native files before any run.**
Nothing below converts a frame; each side's points are written in its own
solver's frame, and the pairing is the literal table :data:`PROBES`.

- cardiacFOAM (``NiedererEtAl2011verification``):
  ``constant/electroProperties``, ``monodomainSolverCoeffs.externalStimulus``,
  is the box ``stimulusLocationMin (0 0 5.5e-3)`` to
  ``stimulusLocationMax (1.5e-3 1.5e-3 7e-3)`` m, so the stimulus corner is
  (0, 0, 7) mm. ``system/blockMeshDict`` spans x 0-20, y 0-3, z 0-7 mm
  (``scale 0.001``). The conductivity tensor (xx xy xz yy yz zz) is
  (0.1334 0 0 0.0176 0 0.0176) S/m, so the fibres run along x.
- The reference frame (``benchmarks/niederer2011.json``): origin at P1, the
  stimulus corner; axis a along the 20 mm (fibre) edge, b along the 7 mm
  edge, c along the 3 mm edge, each pointing into the slab. So, in mm,
  x = a, y = c and z = 7 - b, and cardiacFOAM probe ``k`` of
  ``system/Niedererpoints`` is P(k+1) (:data:`PROBES`). This is the owner's
  convention, confirmed here against the stimulus box, not taken from it.
- openCARP (``02_EP_tissue/03E_study_resolution``): ``nversion.par``'s
  ``stim[0].elec`` is the box p0 (0, 0, 0) to p1 (1500, 1500, 1500) µm, and
  the record's ``mesher`` slab spans 0-20000 x 0-7000 x 0-3000 µm with
  fibres along x (``docs/solver-learning/opencarp.md`` F3). openCARP's
  frame is the reference frame, in µm: its points are the reference's own
  coordinates, in the reference's unit (mm; core converts to the reader's
  µm).

**Pre-registered (topic B Task 8, 2026-09-26), before either run was
read, and not to be changed after:** everything in the module constants
below, and the request built from them in the test. Both solvers use the
same dx (0.5 mm) and the same time step (0.01 ms) for 200 ms, the native
``cartesianConvergence`` study's own ``endTime`` for dx 0.5 mm
(``setup/studies/cartesianConvergence/sweep_hex_convergence.json``). That
is past the ~143 ms cardiacFOAM needed for its slowest probe at dx 0.5 mm
(``docs/solver-learning/cardiacfoam.md`` Q7) and the ~126 ms openCARP needed
for P8 at dx 500 µm, dt 50 µs (``opencarp.md`` G4). A point either solver
does not reach fails the report (``both_not_reached: "fail"``) and fails
this test's premise, never silently.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from foamlib import FoamFieldFile, FoamFile

from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT
from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import experiment_comparisons, load_point_reference
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from cardiacfoam_native import NIEDERER_2011_RELPATH, native_tutorials_root, niederer_sweep, require_sourced_openfoam

#: Needs both native environments: the cardiacFOAM tree with OpenFOAM
#: sourced, and openCARP's tutorials tree with its binary. Each marker fails,
#: never skips, when its environment is missing.
pytestmark = [pytest.mark.native, pytest.mark.native_opencarp]

REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
_OPENCARP_NATIVE = Path(__file__).resolve().parents[2] / "omnidriver-opencarp" / "tests" / "opencarp_native.py"

# --- pre-registered: the same resolution, step and duration on both sides ---
CARDIACFOAM_DX_M = 0.0005          # the record's dx axis, metres
OPENCARP_DX_UM = 500.0             # the record's dx axis, µm: the same 0.5 mm
CARDIACFOAM_DELTA_T_S = 1e-5       # system/controlDict:deltaT, the native value
OPENCARP_DT_US = 10.0              # nversion.par:dt, µs (opencarp.md G2): the same 0.01 ms
CARDIACFOAM_END_TIME_S = 0.2       # system/controlDict:endTime
OPENCARP_TEND_MS = 200.0           # nversion.par:tend, ms: the same 200 ms
TOLERANCE_MS = 5.0
TOLERANCE_RATIONALE = (
    "declared before either run was read; exploratory, not a benchmark acceptance claim. Two discretisations at "
    "dx 0.5 mm (openCARP P1 finite elements, read at mesh nodes; cardiacFOAM finite volumes, read at the "
    "containing cell's centre, up to 0.433 mm from the point) are expected to differ. 5 ms is the bound Tasks 6 "
    "and 7 used, and about half the 10.9 ms spread of P8 across the paper's codes at its finest resolution "
    "(37.8-48.7 ms, section 6)"
)
#: A point either solver leaves unactivated by 200 ms means the duration was
#: too short for that point; it must fail the report, not agree.
BOTH_NOT_REACHED = "fail"
#: cardiacFOAM samples the containing cell's centre: at most half a cell
#: diagonal from any point inside the cell, rounded up at 0.1 µm because the
#: slab's corner probes sit exactly on that bound (as Task 7 pre-registered).
CARDIACFOAM_MAX_OFFSET_M = math.ceil(math.sqrt(3) / 2 * CARDIACFOAM_DX_M * 1e7) / 1e7
#: openCARP samples the nearest mesh node. At dx 500 µm every P1-P9 is a
#: node of the slab (F3's 41 x 15 x 7 grid), so any offset beyond rounding is
#: an orientation error. In the reference's unit, mm: 1 µm.
OPENCARP_MAX_OFFSET_MM = 0.001

#: The agent's pairing, written from the orientation above:
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
_FOUND = re.compile(r"probes : found point \(([^()]*)\) in cell (\d+)")


def _note(probe: str) -> str:
    at, label, reference_at = PROBES[probe]
    return (f"{label} {list(reference_at)} mm in the reference frame. openCARP: the reference frame itself, in um "
            f"(stimulus box at the origin, nversion.par stim[0].elec; F3 slab). cardiacFOAM probe {probe} at "
            f"{list(at)} m in its own frame (system/Niedererpoints), where x = a, y = c, z = 7 mm - b, because "
            "constant/electroProperties puts the stimulus box at the corner (0, 0, 7) mm")


def _opencarp_native() -> ModuleType:
    """openCARP's own native helper, loaded from its file. This module lives
    in cardiacFOAM's tests, and a per-package run of them
    (``packages/omnidriver-cardiacfoam/pyproject.toml``, ``pythonpath =
    ["tests"]``) does not put openCARP's tests on ``sys.path``."""
    spec = importlib.util.spec_from_file_location("opencarp_native_for_cross_solver", _OPENCARP_NATIVE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module     # its dataclass resolves its own module while it executes
    spec.loader.exec_module(module)
    return module


def _artifact_id(output: Path, case, artifact_format: str) -> str:
    document = json.loads((output / case.run_document_path).read_text())
    (artifact,) = [a for a in document["expectedArtifacts"] if a["format"] == artifact_format]
    return artifact["artifact_id"]


def _latest_time(case: Path) -> Path:
    times = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.eE+-]+", p.name) and p.name != "0"]
    return max(times, key=lambda p: float(p.name))


def _containing_cell_centres(case_root: Path, scratch: Path) -> list[tuple[float, ...]]:
    """Each probe's containing-cell centre, as the solver itself reports it:
    OpenFOAM's ``probes`` names the cell it found for each point only under
    ``-debug-switch probes=1`` (``cardiacfoam.md`` Q3), run on a copy of the
    case so the compared run is untouched, and the centre is that cell's
    entry in the ``C`` the run's ``writeCellCentres`` step wrote."""
    require_sourced_openfoam("postProcess")
    copy = scratch / "case"
    shutil.copytree(case_root, copy)
    proc = subprocess.run(["postProcess", "-func", "Niedererpoints", "-debug-switch", "probes=1", "-latestTime"],
                          cwd=copy, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    cells = [int(cell) for _, cell in _FOUND.findall(proc.stdout + proc.stderr)]
    assert len(cells) == len(PROBES), (proc.stdout + proc.stderr)[-2000:]
    centres = FoamFieldFile(_latest_time(case_root) / "C").internal_field
    return [tuple(float(v) for v in centres[cell]) for cell in cells]


def _slab_nodes(case_root: Path) -> list[tuple[float, float, float]]:
    """The openCARP mesh's nodes, µm: the record's ``mesher ... -mesh slab``
    writes ``slab.pts``, a point count and then ``x y z`` per node (F3)."""
    count, *rows = (case_root / "slab.pts").read_text().split("\n")
    nodes = [tuple(float(v) for v in row.split()) for row in rows if row.strip()]
    assert len(nodes) == int(count)
    return nodes


def test_an_agent_compares_opencarp_with_cardiacfoam_at_p1_to_p9(tmp_path):
    # The orientation's drift gate: the pairing above names the probes the
    # native case configures, in its order.
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

    cf_centres = _containing_cell_centres(cf_output / cf_case.case_root, tmp_path / "cardiacfoam")
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
        # openCARP: declared and reported in ms, linearly interpolated at
        # the requested point (a mesh node here, dx 0.5 mm), in its own µm.
        assert (oc["declared_unit"], oc["unit"], oc["sampling_rule"], oc["sampled_at_unit"], oc["requested_at_unit"]) == (
            "ms", "ms", "linear", "um", "um")
        assert oc["requested_at"] == [1000.0 * v for v in reference_at]
        assert tuple(oc["sampled_at"]) in oc_nodes
        assert math.dist(oc["sampled_at"], oc["requested_at"]) == min(math.dist(n, oc["requested_at"]) for n in oc_nodes)
        # cardiacFOAM: declared in s, reported in ms, at the containing
        # cell's centre as the solver reports it, in its own metres.
        assert (cf["declared_unit"], cf["unit"], cf["sampling_rule"], cf["sampled_at_unit"], cf["requested_at_unit"]) == (
            "s", "ms", "cell-containing", "m", "m")
        assert cf["requested_at"] == list(at)
        assert tuple(cf["sampled_at"]) == cf_centres[k]
        assert metric["status"] in {"within_tolerance", "outside_tolerance", "sampled_off_point"}
    for side, max_offset in (("opencarp", OPENCARP_MAX_OFFSET_MM * 1000.0), ("cardiacfoam", CARDIACFOAM_MAX_OFFSET_M)):
        assert report["runs"][side]["max_sampling_offset"] == pytest.approx(max_offset)
    for output in (oc_output, cf_output):
        experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
        assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
        assert {case.comparison.status for case in experiment.cases} == {report["status"]}
