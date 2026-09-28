#!/usr/bin/env python3
"""Write the campaign's pre-registered comparison requests, or check them.

    python write_requests.py           # (re)write requests/*.json and requests/SHA256SUMS
    python write_requests.py --check   # exit 1 unless the committed files are what this writes
    python write_requests.py --check --native-tutorials <cardiacFOAM tutorials>
                                       # also: PROBES and openCARP's grid still match the native case

The requests are the pre-registration; this file is only how they were
typed. Everything a request decides is stated here, above any run: the
tolerances and their rationale, ``both_not_reached``, each side's points in
its own solver's frame, each side's ``max_sampling_offset``, and the pairing.
Revise it (README, "Pre-registration") only before the campaign's first
run; afterwards a changed request is a new request with its own report.

Every path in a request is relative, and ``omnidriver compare`` resolves it
against the request's own directory. So a request's bytes, and its digest,
are the same on every machine and for every run: nothing is filled in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQUESTS = HERE / "requests"
REFERENCE = HERE.parents[1] / "niederer2011.json"
#: From a request's directory (requests/) to the reference and to each sweep.
REFERENCE_FROM_REQUEST = "../../../niederer2011.json"
STUDY = "cartesianConvergence"
OPENCARP_STUDY = HERE / "studies" / f"opencarp_{STUDY}.json"
#: The native case and study cardiacFOAM runs, under its tutorials tree.
NATIVE_CASE = "NiedererEtAl2011verification"
NATIVE_STUDY = f"{NATIVE_CASE}/setup/studies/{STUDY}/sweep_hex_convergence.json"

#: The paper's grid (section 3d), in mm and ms. A level study keeps its rows
#: in this order, so the time steps are case_0001, case_0002, case_0003 of
#: each dx's sweep (README, "Levels and case ids").
DX_MM = (0.5, 0.2, 0.1)
DT_MS = (0.05, 0.01, 0.005)
#: cardiacFOAM's native cartesianConvergence endTime per dx, and openCARP's
#: study matches it (studies/opencarp_cartesianConvergence.json).
END_MS = {0.5: 200, 0.2: 80, 0.1: 55}

CROSS_TOLERANCE = {
    "kind": "absolute", "value": 5.0, "unit": "ms",
    "rationale": (
        "Pre-registered 2026-09-27 for the whole campaign, before any campaign run. The same bar at every level, "
        "so the nine reports say at which (dx, dt) openCARP and cardiacFOAM agree to it; a coarse level outside it "
        "is a finding, not a reason to loosen it. 5 ms is about half the 10.9 ms spread of P8 across the paper's "
        "codes at its finest level (37.8-48.7 ms, section 6), so passing means agreeing more closely than two of "
        "the paper's codes may. Two discretisations are compared: openCARP P1 finite elements with a full mass "
        "matrix, read at the nearest node; cardiacFOAM finite volumes, read at the containing cell's centre. Topic B "
        "Task 8 (cardiacfoam.md section X) saw dx 0.5 mm, dt 0.01 ms with openCARP's lumped mass; this bar is the "
        "5 ms Task 8 fixed before its own runs, not chosen from its numbers"
    ),
}
TEMPORAL_TOLERANCE = {
    "kind": "absolute", "value": 1.0, "unit": "ms",
    "rationale": (
        "Pre-registered 2026-09-27, before any campaign run: the owner's belief that the time step barely matters, "
        "made testable. Two successive time steps of one solver at one dx 'agree' when no point moves by more than "
        "1 ms: a fifth of the cross-solver bar, so a time-step effect inside it cannot by itself decide a "
        "cross-solver verdict, and 20 times the coarsest step (0.05 ms), so the step's own quantisation of the "
        "0 mV crossing cannot fail it. Seen before: openCARP P8 moved 0.19 ms between dt 50 and 10 us at dx "
        "0.5 mm with lumped mass (opencarp.md G4, G9); cardiacFOAM's time-step effect has not been measured"
    ),
}
BOTH_NOT_REACHED = "fail"   # every end time was chosen so every point activates; a point that does not is a failure

#: The probe pairing (cardiacfoam.md section X), read from
#: the native files: cardiacFOAM's stimulus box sits at the corner
#: (0, 0, 7) mm of its 20 x 3 x 7 mm slab, fibres along x, so x = a, y = c,
#: z = 7 mm - b, and probe k of system/Niedererpoints is P(k+1). Its expected
#: locations are that file's probeLocations, in m, unconverted.
PROBES = {
    "P1": ("0", (0.0, 0.0, 0.007)), "P2": ("1", (0.0, 0.0, 0.0)),
    "P3": ("2", (0.019999, 0.0, 0.007)), "P4": ("3", (0.019999, 0.0, 0.0)),
    "P5": ("4", (0.0, 0.003, 0.007)), "P6": ("5", (0.0, 0.003, 0.0)),
    "P7": ("6", (0.019999, 0.003, 0.007)), "P8": ("7", (0.019999, 0.003, 0.0)),
    "P9": ("8", (0.01, 0.0015, 0.0035)),
}
ORIENTATION = (
    "openCARP: the reference frame itself (nversion.par stim[0].elec at the origin; opencarp.md F3 slab), points in "
    "the reference's mm. cardiacFOAM: probe {probe} at {at} m of system/Niedererpoints, in its own frame, where "
    "x = a, y = c, z = 7 mm - b (constant/electroProperties puts the stimulus box at the corner (0, 0, 7) mm)"
)


def _reference_points() -> dict[str, list[float]]:
    return {p["label"]: p["coordinates"] for p in json.loads(REFERENCE.read_text())["points"]}


def _ceil(value: float, step: float) -> float:
    return round(math.ceil(value / step - 1e-9) * step, 10)


def _opencarp_offset_mm(dx_mm: float, points: dict[str, list[float]]) -> float:
    """openCARP reads the nearest node of a grid of spacing dx from the
    origin. The bound is the farthest any P is from its nearest node (P9 at
    dx 0.2 mm: 0.1414 mm; every P is a node at 0.5 and 0.1 mm), rounded up at
    0.1 um, and at least 1 um, so anything more is an orientation error."""
    far = max(math.dist(p, [round(c / dx_mm) * dx_mm for c in p]) for p in points.values())
    return max(0.001, _ceil(far, 0.0001))


def _cardiacfoam_offset_m(dx_mm: float) -> float:
    """cardiacFOAM reports the containing cell's centre: at most half a cell
    diagonal away, rounded up at 0.1 um (corner probes sit on that bound)."""
    return _ceil(math.sqrt(3) / 2 * dx_mm * 1e-3, 1e-7)


def _level(dx_mm: float, dt_ms: float) -> str:
    return f"dx{dx_mm:g}_dt{dt_ms:g}"


def _run(solver: str, dx_mm: float, dt_ms: float, points: dict[str, list[float]]) -> dict:
    case_id = f"case_{DT_MS.index(dt_ms) + 1:04d}"
    sweep = f"../runs/{solver}/{STUDY}/dx{dx_mm:g}"
    if solver == "opencarp":
        return {"plugin": "opencarp", "sweep_output": sweep, "case_id": case_id, "artifact_id": "record.solve.2",
                "points": {"unit": "mm", "at": points}, "max_sampling_offset": _opencarp_offset_mm(dx_mm, points)}
    return {"plugin": "cardiacfoam", "sweep_output": sweep, "case_id": case_id, "artifact_id": "record.samplePoints.0",
            "points": {"unit": "m", "at": {probe: list(at) for probe, at in PROBES.values()}},
            "max_sampling_offset": _cardiacfoam_offset_m(dx_mm)}


def _quantity(solver: str, label: str) -> str:
    return label if solver == "opencarp" else PROBES[label][0]


def _describe(solver: str, dx_mm: float, dt_ms: float) -> str:
    case_id = f"case_{DT_MS.index(dt_ms) + 1:04d}"
    if solver == "opencarp":
        values = f"dx {dx_mm * 1000:g} um, nversion.par:dt {dt_ms * 1000:g} us, tend {END_MS[dx_mm]} ms"
    else:
        values = f"dx {dx_mm / 1000:g} m, deltaT {dt_ms / 1000:g} s, endTime {END_MS[dx_mm] / 1000:g} s"
    return f"{solver} {case_id} of runs/{solver}/{STUDY}/dx{dx_mm:g} ({values})"


def _request(runs: dict, pairs: list, tolerance: dict) -> dict:
    return {"schema_version": 1, "reference": REFERENCE_FROM_REQUEST, "tolerance": tolerance,
            "both_not_reached": BOTH_NOT_REACHED, "runs": runs, "pairs": pairs}


def requests() -> dict[str, dict]:
    points = _reference_points()
    written: dict[str, dict] = {}
    for dx in DX_MM:
        for dt in DT_MS:
            level = f"dx {dx:g} mm, dt {dt:g} ms"
            pairs = [{"reference_label": label, "left": {"run": "opencarp", "quantity": label},
                      "right": {"run": "cardiacfoam", "quantity": _quantity("cardiacfoam", label)},
                      "note": (f"{label} {points[label]} mm in the reference frame; level {level}: "
                               f"{_describe('opencarp', dx, dt)} against {_describe('cardiacfoam', dx, dt)}. "
                               + ORIENTATION.format(probe=PROBES[label][0], at=list(PROBES[label][1])))}
                     for label in PROBES]
            written[f"cross_{_level(dx, dt)}"] = _request(
                {"opencarp": _run("opencarp", dx, dt, points), "cardiacfoam": _run("cardiacfoam", dx, dt, points)},
                pairs, CROSS_TOLERANCE)
        for solver in ("opencarp", "cardiacfoam"):
            for coarse, fine in zip(DT_MS, DT_MS[1:]):
                left, right = f"dt{coarse:g}", f"dt{fine:g}"
                pairs = [{"reference_label": label, "left": {"run": left, "quantity": _quantity(solver, label)},
                          "right": {"run": right, "quantity": _quantity(solver, label)},
                          "note": (f"{label} {points[label]} mm in the reference frame; one solver, one frame, "
                                   f"dx {dx:g} mm: {_describe(solver, dx, coarse)} against "
                                   f"{_describe(solver, dx, fine)}")}
                         for label in PROBES]
                written[f"temporal_{solver}_dx{dx:g}_dt{coarse:g}_vs_dt{fine:g}"] = _request(
                    {left: _run(solver, dx, coarse, points), right: _run(solver, dx, fine, points)},
                    pairs, TEMPORAL_TOLERANCE)
    return written


def rendered() -> dict[str, bytes]:
    files = {f"{name}.json": (json.dumps(request, indent=2) + "\n").encode() for name, request in requests().items()}
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))
    return {**files, "SHA256SUMS": sums.encode()}


def native_drift(tutorials: Path) -> list[str]:
    """What no longer matches the native cardiacFOAM case: its probes (the
    pairing's expected locations) and its study's grid, against openCARP's
    study in openCARP's units (dx um, dt us, tend ms; opencarp.md G2)."""
    from foamlib import FoamFile

    problems = []
    probes = [list(map(float, at)) for at in FoamFile(tutorials / NATIVE_CASE / "system" / "Niedererpoints")["probeLocations"]]
    if probes != [list(at) for _, at in PROBES.values()]:
        problems.append(f"system/Niedererpoints probeLocations {probes} are not PROBES")
    native = json.loads((tutorials / NATIVE_STUDY).read_text())["sweep"]["independent"]
    ours = json.loads(OPENCARP_STUDY.read_text())["sweep"]["independent"]
    grid = list(zip(native["dx"], native["system/controlDict:deltaT"], native["system/controlDict:endTime"]))
    same = list(zip((v * 1e-6 for v in ours["dx"]), (v * 1e-6 for v in ours["nversion.par:dt"]),
                    (v * 1e-3 for v in ours["nversion.par:tend"])))
    if len(grid) != len(same) or any(not math.isclose(a, b, rel_tol=1e-9) for g, o in zip(grid, same) for a, b in zip(g, o)):
        problems.append(f"{OPENCARP_STUDY.name}'s grid {same} is not the native study's {grid}")
    expected = [(dx * 1e-3, dt * 1e-3, END_MS[dx] * 1e-3) for dx in DX_MM for dt in DT_MS]
    if any(not math.isclose(a, b, rel_tol=1e-9) for g, e in zip(grid, expected) for a, b in zip(g, e)) or len(grid) != 9:
        problems.append(f"the native study's grid {grid} is not DX_MM x DT_MS with END_MS, in that order")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="compare the committed files with what this writes")
    parser.add_argument("--native-tutorials", type=Path, help="with --check: also check against the native cardiacFOAM case")
    args = parser.parse_args(argv)
    files = rendered()
    if args.check:
        present = {path.name for path in REQUESTS.iterdir()} if REQUESTS.is_dir() else set()
        wrong = sorted(name for name, data in files.items()
                       if not (REQUESTS / name).is_file() or (REQUESTS / name).read_bytes() != data)
        extra = sorted(present - set(files))
        for name in wrong:
            print(f"differs or missing: requests/{name}", file=sys.stderr)
        for name in extra:
            print(f"not written by this script: requests/{name}", file=sys.stderr)
        drift = native_drift(args.native_tutorials) if args.native_tutorials else []
        for problem in drift:
            print(f"native drift: {problem}", file=sys.stderr)
        if wrong or extra or drift:
            return 1
        if args.native_tutorials:
            print(f"the native case at {args.native_tutorials} still matches PROBES and the grid")
        print(f"requests/ matches: {len(files) - 1} requests and SHA256SUMS")
        return 0
    REQUESTS.mkdir(exist_ok=True)
    for name, data in files.items():
        (REQUESTS / name).write_bytes(data)
    print(f"wrote {len(files) - 1} requests and SHA256SUMS to {REQUESTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
