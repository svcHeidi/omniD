"""One trial: a fresh folder, the condition's PATH and guidance, the agent, the oracle, and the record."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import Adapter, AdapterResult
from .guidance import load_guidance
from .shims import write_shims
from .task import Task
from .tree import digest_tree, export_tree

CONDITIONS = ("omnid", "bare")
ORACLE_TIMEOUT = 600


@dataclass(frozen=True)
class TrialSetup:
    output: Path
    condition: str
    omnid_repo: Path
    omnidriver_bin: Path
    agent_python: Path
    agent_home: Path
    solver_path: tuple[Path, ...] = ()
    extra_env: dict[str, str] = field(default_factory=dict)
    oracle_env: dict[str, str] = field(default_factory=dict)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item["text"] for item in value if isinstance(item, dict) and isinstance(item.get("text"), str)]
    return []


def _is_refusal(content) -> bool:
    for text in _strings(content):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("status") == "failed":
            return True
    return False


def _refusals(transcript: list[dict]) -> int:
    """Tool results of an ``omnidriver`` command that carry omniD's refusal shape."""
    items = [item for event in transcript for item in (event.get("message") or {}).get("content") or []
             if isinstance(item, dict)]
    calls = {item["id"] for item in items if item.get("type") == "tool_use"
             and isinstance((item.get("input") or {}).get("command"), str) and "omnidriver" in item["input"]["command"]}
    return sum(1 for item in items if item.get("type") == "tool_result" and item.get("tool_use_id") in calls
               and _is_refusal(item.get("content")))


def _field(data: dict, dotted: str):
    for part in dotted.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _inside_repository(path: Path) -> bool:
    existing = path
    while not existing.exists():
        existing = existing.parent
    return subprocess.run(["git", "-C", str(existing), "rev-parse", "--is-inside-work-tree"],
                          capture_output=True).returncode == 0


def _judge(task: Task, work: Path, env: dict[str, str]) -> dict:
    argv = [a.replace("{trial}", str(work)) for a in task.oracle.argv]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=ORACLE_TIMEOUT)
    except FileNotFoundError as exc:
        return {"oracle_error": f"cannot start the oracle: {exc}"}
    except subprocess.TimeoutExpired:
        return {"oracle_error": f"timed out after {ORACLE_TIMEOUT} s"}
    if done.returncode != 0:
        return {"oracle_error": f"exit {done.returncode}: {done.stderr[-2000:]}"}
    try:
        verdict = json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"oracle_error": f"undecodable output: {done.stdout[-2000:]}"}
    return verdict if isinstance(verdict, dict) else {"oracle_error": f"not a JSON object: {done.stdout[-2000:]}"}


def run_trial(task: Task, adapter: Adapter, setup: TrialSetup, index: int) -> dict:
    """Run ``task`` once under ``adapter`` in ``setup.condition`` and write its record."""
    if setup.condition not in CONDITIONS:
        raise ValueError(f"condition {setup.condition!r} is not one of {CONDITIONS}")
    for name in ("output", "agent_home"):
        if _inside_repository(getattr(setup, name)):
            raise ValueError(f"{name} {getattr(setup, name)} is inside a git repository")
    if subprocess.run([str(setup.agent_python), "-c", "import omnidriver"], capture_output=True).returncode == 0:
        raise ValueError(f"agent_python {setup.agent_python} can import omnidriver")
    omnid_commit = _git(setup.omnid_repo, "rev-parse", "HEAD")
    omnid_dirty = bool(_git(setup.omnid_repo, "status", "--porcelain"))
    folder = setup.output / uuid.uuid4().hex
    work, shims, tools, omnid_bin = folder / "work", folder / "shims", folder / "tools", folder / "omnid-bin"
    work.mkdir(parents=True)
    setup.agent_home.mkdir(parents=True, exist_ok=True)
    tools.mkdir()
    omnid_bin.mkdir()
    for name in ("python3", "python"):
        (tools / name).symlink_to(setup.agent_python)
    (omnid_bin / "omnidriver").symlink_to(setup.omnidriver_bin)
    launches = folder / "launches.jsonl"
    write_shims(shims, task.programs, launches, setup.agent_python)
    tree_commit = tree_before = None
    if task.tree:
        tree_commit = export_tree(Path(task.tree["git_dir"]), task.tree["ref"], work / "tree")
        tree_before = digest_tree(work / "tree")
    agent_path = [str(shims), str(tools), *map(str, setup.solver_path)]
    if setup.condition == "omnid":
        agent_path.append(str(omnid_bin))
    env = {**setup.extra_env, "HOME": str(setup.agent_home), "SHELL": "/bin/bash",
           "PATH": os.pathsep.join([*agent_path, "/usr/bin", "/bin"])}
    guidance = load_guidance(setup.omnid_repo, task.role) if setup.condition == "omnid" else None
    harness_error = None
    start = time.monotonic()
    try:
        result = adapter.run(task.brief.replace("{trial}", str(work)), guidance.text if guidance else None,
                             work, env, task.wall_seconds)
    except Exception as exc:
        harness_error = f"adapter: {exc!r}"
        result = AdapterResult(final_text="", transcript=[], turns=0, cost_usd=None, is_error=True)
    seconds = round(time.monotonic() - start, 3)
    verdict = {}
    try:
        verdict = _judge(task, work, {**env, **setup.oracle_env, "PATH": os.pathsep.join([str(omnid_bin), env["PATH"]])})
    except Exception as exc:
        harness_error = harness_error or f"oracle: {exc!r}"
    with (folder / "transcript.jsonl").open("w") as f:
        f.writelines(json.dumps(e) + "\n" for e in result.transcript)
    launch_lines = launches.read_text().splitlines() if launches.exists() else []
    record = {
        "task": task.id, "task_digest": task.digest, "role": task.role, "condition": setup.condition,
        "adapter": adapter.name, "adapter_version": adapter.version(), "index": index,
        "model_resolved": result.init.get("model"),
        "isolation": {k: result.init.get(k) for k in ("plugins", "mcp_servers", "hooks_seen")},
        "omnid_commit": omnid_commit, "omnid_dirty": omnid_dirty,
        "guidance": [list(f) for f in guidance.files] if guidance else [],
        "seconds": seconds, "turns": result.turns, "cost_usd": result.cost_usd, "usage": result.usage,
        "is_error": result.is_error, "timed_out": result.timed_out, "undecodable_lines": result.undecodable_lines,
        "final_text": result.final_text,
        "launches": len(launch_lines),
        "failed_launches": sum(1 for line in launch_lines if json.loads(line)["exit_code"] != 0),
        "refusals": _refusals(result.transcript),
        "tree_commit": tree_commit, "tree_before": tree_before,
        "tree_after": digest_tree(work / "tree") if task.tree else None,
        "oracle": verdict, "harness_error": harness_error,
        "success": harness_error is None and "oracle_error" not in verdict
        and _field(verdict, task.oracle.pass_field) in task.oracle.pass_values,
    }
    (folder / "task_record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
