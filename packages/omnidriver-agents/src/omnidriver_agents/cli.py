"""``omnidriver-agents run`` and ``summarize``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.claude_code import ClaudeCodeAdapter
from .summary import summarize
from .task import load_task
from .trial import CONDITIONS, TrialSetup, run_trial


def _pairs(values: list[str], flag: str) -> dict[str, str]:
    out = {}
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep:
            raise SystemExit(f"{flag} {value!r}: expected NAME=VALUE")
        out[name] = rest
    return out


def main(argv: list[str] | None = None) -> int:
    """Run a task across models and conditions, or summarize a results folder."""
    parser = argparse.ArgumentParser(prog="omnidriver-agents")
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--input", action="append", default=[])
    run.add_argument("--model", action="append", required=True)
    run.add_argument("--condition", action="append", choices=CONDITIONS, required=True)
    run.add_argument("--repeats", type=int, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--omnid-repo", type=Path, required=True)
    run.add_argument("--omnidriver", type=Path, required=True)
    run.add_argument("--claude", type=Path, required=True)
    run.add_argument("--solver-path", type=Path, action="append", default=[])
    run.add_argument("--env", action="append", default=[])
    summary = sub.add_parser("summarize")
    summary.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    if args.action == "summarize":
        print(json.dumps(summarize(args.output), indent=2))
        return 0
    task = load_task(args.task, _pairs(args.input, "--input"))
    for model in args.model:
        adapter = ClaudeCodeAdapter(model=model, executable=args.claude)
        for condition in args.condition:
            setup = TrialSetup(output=args.output, condition=condition, omnid_repo=args.omnid_repo,
                               omnidriver_bin=args.omnidriver, solver_path=tuple(args.solver_path),
                               extra_env=_pairs(args.env, "--env"))
            for index in range(args.repeats):
                record = run_trial(task, adapter, setup, index)
                print(json.dumps({k: record[k] for k in ("task", "adapter", "condition", "index", "success", "seconds")}))
    return 0
