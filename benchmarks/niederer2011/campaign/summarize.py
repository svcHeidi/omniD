#!/usr/bin/env python3
"""Tables from what the campaign's runs and reports already record.

    python summarize.py [--runs runs]

Reads, and writes nothing:
- every sweep under ``runs/`` (any ``sweep_manifest.json``): each case's
  study values, status, rank count and per-step wall times, from its
  ``workflow_state.json`` (each step's ``started_at``/``finished_at``) and
  its solve step's command (``mpirun -np N``; otherwise one process);
- every report under ``runs/reports/``: its status, request digest and
  pairs, and whether core associates it with each case it names
  (``run_verified``);
- from the cross-solver reports: time to accuracy, P8 per level against each
  solver's own finest level and against the paper's published range
  (``benchmarks/niederer2011.json`` ``published_values``, read, not restated).

Step groups follow the records' own step ids: ``solve`` is the solve;
``solve.*`` is the parallel form's decomposition and reconstruction; every
other step is meshing (before the solve) or post-processing (after it).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import experiment_comparisons

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parents[1] / "niederer2011.json"


def _seconds(step: dict) -> float | None:
    if not step.get("started_at") or not step.get("finished_at"):
        return None
    return (datetime.fromisoformat(step["finished_at"]) - datetime.fromisoformat(step["started_at"])).total_seconds()


def _case_timings(state: dict) -> dict:
    groups = {"mesh": 0.0, "solve": None, "decompose/reconstruct": 0.0, "post": 0.0}
    ranks, seen_solve = 1, False
    for step in state.get("steps", ()):
        seconds = _seconds(step) or 0.0
        step_id = step["step_id"]
        if step_id == "solve":
            groups["solve"], seen_solve = seconds, True
            if step["command"] == "mpirun" and "-np" in step["args"]:
                ranks = int(step["args"][step["args"].index("-np") + 1])
        elif step_id.startswith("solve."):
            groups["decompose/reconstruct"] += seconds
        else:
            groups["post" if seen_solve else "mesh"] += seconds
    return {"ranks": ranks, **groups}


def sweeps(runs: Path) -> dict[tuple[Path, str], dict]:
    table = {}
    for manifest_path in sorted(runs.rglob("sweep_manifest.json")):
        output = manifest_path.parent
        for case in json.loads(manifest_path.read_text()).get("cases", ()):
            state_path = output / case["workflow_state_path"]
            state = json.loads(state_path.read_text()) if state_path.is_file() else {}
            table[(output.resolve(), case["case_id"])] = {
                "sweep": output.relative_to(runs) if output.is_relative_to(runs) else output,
                "values": case.get("resolved_axis_values", {}), "status": state.get("status", "not_run"),
                **_case_timings(state)}
    return table


def _fmt(value, digits: int = 3) -> str:
    return "—" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=Path, default=HERE / "runs")
    args = parser.parse_args(argv)
    runs = args.runs.resolve()
    cases = sweeps(runs)

    print("## Runs (wall seconds per step group)\n")
    print("| sweep | case | study values | status | ranks | mesh | solve | decompose/reconstruct | post |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (_, case_id), row in cases.items():
        values = ", ".join(f"{k} {v}" for k, v in row["values"].items())
        print(f"| {row['sweep']} | {case_id} | {values} | {row['status']} | {row['ranks']} | {_fmt(row['mesh'], 1)} "
              f"| {_fmt(row['solve'], 1)} | {_fmt(row['decompose/reconstruct'], 1)} | {_fmt(row['post'], 1)} |")

    reports = sorted((runs / "reports").glob("*.json")) if (runs / "reports").is_dir() else []
    p8: dict[tuple[str, str], tuple[float | None, dict]] = {}
    for path in reports:
        report = json.loads(path.read_text())
        print(f"\n## {path.stem}: `{report['status']}`\n")
        print(f"request `{report['request']['digest']}`; tolerance {report['metrics'][0]['tolerance']['value']} "
              f"{report['metrics'][0]['tolerance'].get('unit', '(relative)')}; runs: "
              + "; ".join(f"{name} = {Path(run['sweep_output']).name}/{run['case_id']} "
                          f"{cases.get((Path(run['sweep_output']).resolve(), run['case_id']), {}).get('values')}"
                          for name, run in report["runs"].items()) + "\n")
        # Core checks each case the report names against the case's own
        # recorded digests (quantities.experiment_comparisons); it never takes
        # the report's word for which case it covers.
        associations = []
        for sweep_output in dict.fromkeys(run["sweep_output"] for run in report["runs"].values()):
            experiment = inspect_sweep_experiment(
                sweep_output, comparisons=experiment_comparisons(path, sweep_output=sweep_output))
            associations += [f"{Path(sweep_output).name}/{case.case_id} {case.comparison.association_status}"
                             for case in experiment.cases if case.comparison is not None
                             and case.comparison.association_status != "not_requested"]
        print("association: " + "; ".join(associations) + "\n")
        left, right = report["metrics"][0]["left"]["run"], report["metrics"][0]["right"]["run"]
        print(f"| point | {left} (ms) | {right} (ms) | difference (ms) | status |")
        print("|---|---|---|---|---|")
        for metric in report["metrics"]:
            print(f"| {metric['reference_label']} | {_fmt(metric['left']['value'])} | {_fmt(metric['right']['value'])} "
                  f"| {_fmt(metric['difference'])} | {metric['status']} |")
            if path.stem.startswith("cross_") and metric["reference_label"] == "P8":
                level = path.stem.removeprefix("cross_")
                for side in ("left", "right"):
                    run = report["runs"][metric[side]["run"]]
                    timing = cases.get((Path(run["sweep_output"]).resolve(), run["case_id"]), {})
                    p8[(metric[side]["run"], level)] = (metric[side]["value"], timing)

    if p8:
        published = next(v for v in json.loads(REFERENCE.read_text())["published_values"] if v["label"] == "P8")
        low, high = published["range"]
        print(f"\n## Time to accuracy: P8 (paper, {published['conditions']}: {low}-{high} ms)\n")
        print("| solver | level | ranks | solve (s) | P8 (ms) | P8 - own finest (ms) | in the paper's range |")
        print("|---|---|---|---|---|---|---|")
        for (solver, level), (value, timing) in sorted(p8.items()):
            finest = p8.get((solver, "dx0.1_dt0.005"), (None, {}))[0]
            error = None if value is None or finest is None else value - finest
            inside = "—" if value is None else ("yes" if low <= value <= high else "no")
            print(f"| {solver} | {level} | {timing.get('ranks', '—')} | {_fmt(timing.get('solve'), 1)} "
                  f"| {_fmt(value)} | {_fmt(error)} | {inside} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
