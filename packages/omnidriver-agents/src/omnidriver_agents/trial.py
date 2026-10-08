"""One trial: a fresh folder, the condition's PATH and guidance, the agent, the oracle, and the record."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import Adapter
from .guidance import load_guidance
from .shims import write_shims
from .task import Task
from .tree import digest_tree, export_tree

CONDITIONS = ("omnid", "bare")


@dataclass(frozen=True)
class TrialSetup:
    output: Path
    condition: str
    omnid_repo: Path
    omnidriver_bin: Path
    solver_path: tuple[Path, ...] = ()
    extra_env: dict[str, str] = field(default_factory=dict)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _refusals(transcript: list[dict]) -> int:
    """Tool results carrying omniD's refusal shape; a tool result's content may be text or nested blocks."""
    return sum(
        1
        for event in transcript
        for item in (event.get("message") or {}).get("content") or []
        if isinstance(item, dict) and item.get("type") == "tool_result"
        and any('"status": "failed"' in text for text in _strings(item.get("content")))
    )


def _field(data: dict, dotted: str):
    for part in dotted.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def run_trial(task: Task, adapter: Adapter, setup: TrialSetup, index: int) -> dict:
    """Run ``task`` once under ``adapter`` in ``setup.condition`` and write its record."""
    if setup.condition not in CONDITIONS:
        raise ValueError(f"condition {setup.condition!r} is not one of {CONDITIONS}")
    folder = setup.output / task.id / adapter.name / setup.condition / str(index)
    work, shims = folder / "work", folder / "shims"
    work.mkdir(parents=True)
    launches = folder / "launches.jsonl"
    write_shims(shims, task.programs, launches)
    tree_commit = tree_before = None
    if task.tree:
        tree_commit = export_tree(Path(task.tree["git_dir"]), task.tree["ref"], work / "tree")
        tree_before = digest_tree(work / "tree")
    omnid_dir = str(setup.omnidriver_bin.parent)
    agent_path = [str(shims), *map(str, setup.solver_path)]
    if setup.condition == "omnid":
        agent_path.append(omnid_dir)
    env = {"HOME": os.environ["HOME"], "PATH": os.pathsep.join([*agent_path, "/usr/bin", "/bin"]), **setup.extra_env}
    guidance = load_guidance(setup.omnid_repo, task.role) if setup.condition == "omnid" else None
    start = time.monotonic()
    result = adapter.run(task.brief.replace("{trial}", str(work)), guidance.text if guidance else None,
                         work, env, task.wall_seconds)
    seconds = round(time.monotonic() - start, 3)
    oracle_env = {**env, "PATH": os.pathsep.join([omnid_dir, env["PATH"]])}
    oracle_run = subprocess.run([a.replace("{trial}", str(work)) for a in task.oracle.argv],
                                capture_output=True, text=True, env=oracle_env)
    try:
        verdict = json.loads(oracle_run.stdout)
    except json.JSONDecodeError:
        verdict = {"oracle_error": oracle_run.stderr[-2000:] or oracle_run.stdout[-2000:]}
    with (folder / "transcript.jsonl").open("w") as f:
        f.writelines(json.dumps(e) + "\n" for e in result.transcript)
    launch_lines = launches.read_text().splitlines() if launches.exists() else []
    record = {
        "task": task.id, "task_digest": task.digest, "role": task.role, "condition": setup.condition,
        "adapter": adapter.name, "adapter_version": adapter.version(), "index": index,
        "omnid_commit": _git(setup.omnid_repo, "rev-parse", "HEAD"),
        "omnid_dirty": bool(_git(setup.omnid_repo, "status", "--porcelain")),
        "guidance": [list(f) for f in guidance.files] if guidance else [],
        "seconds": seconds, "turns": result.turns, "cost_usd": result.cost_usd, "usage": result.usage,
        "is_error": result.is_error, "timed_out": result.timed_out,
        "launches": len(launch_lines),
        "failed_launches": sum(1 for line in launch_lines if json.loads(line)["exit_code"] != 0),
        "refusals": _refusals(result.transcript),
        "tree_commit": tree_commit, "tree_before": tree_before,
        "tree_after": digest_tree(work / "tree") if task.tree else None,
        "oracle": verdict,
        "success": _field(verdict, task.oracle.pass_field) in task.oracle.pass_values,
    }
    (folder / "task_record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
