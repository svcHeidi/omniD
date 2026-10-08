# Agent harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sixth package, `omnidriver-agents`, that runs the same task under several LLM agents, with and without omniD, and writes one task record per trial.

**Architecture:** A standalone package (`omnidriver_agents`, deliberately outside the `omnidriver` namespace) that drives agents through their CLIs in a fresh folder per trial, with PATH built only from supplied directories. It never imports omniD. The judge of a trial is an oracle command named by the task. The spec is `docs/superpowers/specs/2026-10-09-agent-harness-design.md`.

**Tech Stack:** Python ≥3.11, PyYAML (for the guidance manifest), the `claude` CLI (headless `-p`, `stream-json`), pytest.

## Global Constraints

- Imports nothing from `omnidriver` or `omnidriver.*`; nothing in `packages/omnidriver*/src/omnidriver` imports `omnidriver_agents`. Enforced in `scripts/check-import-boundaries.py`.
- No pytest test calls a model or a solver. Tests use `FakeAdapter`.
- Everything is supplied: output root, CLI config folder, solver directories, task inputs. Nothing is searched for.
- House style (`CLAUDE.md`): docstrings on the public surface only, comments only for the non-obvious, no history in code.
- The installed `claude` CLI has no `--max-turns`; the budget is wall time, and turns are recorded, not limited.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Venv for this worktree (memory: a worktree needs its own venv): `uv venv --python 3.11 /tmp/od-agents && VIRTUAL_ENV=/tmp/od-agents uv pip install -q -e packages/omnidriver-agents pytest`. Run everything from `/Users/simaocastro/omnidriver/.claude/worktrees/agents`.

## Files

```
packages/omnidriver-agents/
  pyproject.toml
  src/omnidriver_agents/
    __init__.py
    task.py           Task, Oracle, load_task
    guidance.py       Guidance, load_guidance (provider-integration.md's launcher)
    tree.py           export_tree, digest_tree
    shims.py          write_shims, and the shim's own main
    adapters/__init__.py   AdapterResult, Adapter protocol
    adapters/claude_code.py  ClaudeCodeAdapter, parse_stream
    trial.py          run_trial
    summary.py        summarize
    cli.py            main
  tests/
    conftest.py       FakeAdapter
    test_task.py test_guidance.py test_tree.py test_shims.py
    test_claude_code.py test_trial.py test_summary.py test_cli.py
  tasks/nversion-opencarp/task.json, oracle.py, README.md
scripts/check-import-boundaries.py   (modified)
.github/workflows/ci.yml             (modified: one job)
```

---

### Task 1: Package skeleton and the boundary rule

**Files:**
- Create: `packages/omnidriver-agents/pyproject.toml`, `packages/omnidriver-agents/src/omnidriver_agents/__init__.py`, `packages/omnidriver-agents/tests/test_boundary.py`
- Modify: `scripts/check-import-boundaries.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: importable package `omnidriver_agents`; console script `omnidriver-agents = omnidriver_agents.cli:main` (cli lands in Task 8).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "omnidriver-agents"
version = "0.1.0"
description = "Runs one task under several LLM agents, with and without omniD, and records each trial."
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0"]

[project.scripts]
omnidriver-agents = "omnidriver_agents.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
addopts = "--import-mode=importlib"
```

`src/omnidriver_agents/__init__.py`:

```python
"""Measure LLM agents on omniD tasks, with and without omniD; drives the CLI only."""
```

- [ ] **Step 2: Write the failing test**

`tests/test_boundary.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_import_gate_passes_and_knows_this_package():
    gate = REPO / "scripts/check-import-boundaries.py"
    assert "omnidriver_agents" in gate.read_text()
    result = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
```

- [ ] **Step 3: Run it; expect FAIL** (`"omnidriver_agents" in ...` is false)

Run: `/tmp/od-agents/bin/python -m pytest packages/omnidriver-agents/tests/test_boundary.py -q`

- [ ] **Step 4: Add the rule to the gate**

In `scripts/check-import-boundaries.py`, after `CARDIACFOAM_SRC = ...` add:

```python
# The agent harness measures omniD from outside, through its CLI: importing
# omniD would let the measurement depend on what it measures.
AGENTS_SRC = REPO_ROOT / "packages/omnidriver-agents/src/omnidriver_agents"
```

In `main()`, after the `for root, forbidden in adapter_rules.items():` loop add:

```python
    for path in AGENTS_SRC.rglob("*.py"):
        found.extend(_check_file(path, ("omnidriver",), AGENTS_SRC))
    for path in REPO_ROOT.glob("packages/*/src/omnidriver/**/*.py"):
        found.extend(_check_file(path, ("omnidriver_agents",), REPO_ROOT))
```

and append to the violation message string: `"omnidriver_agents imports no omnidriver package and none imports it. "`.

- [ ] **Step 5: Run the test and the gate; expect PASS / exit 0**

Run: `/tmp/od-agents/bin/python -m pytest packages/omnidriver-agents/tests/test_boundary.py -q && python3 scripts/check-import-boundaries.py`

- [ ] **Step 6: Add a CI job** in `.github/workflows/ci.yml`, copying the `test-opencarp` job's shape: name `test-agents`, cache path `packages/omnidriver-agents/pyproject.toml`, install `pip install -e packages/omnidriver-agents pytest`, run `python -m pytest packages/omnidriver-agents/tests -q`.

- [ ] **Step 7: Commit** — `feat(agents): the harness package, outside omniD's namespace and import graph`

---

### Task 2: Task files

**Files:** Create `src/omnidriver_agents/task.py`, `tests/test_task.py`

**Interfaces:**
- Produces: `Oracle(argv: tuple[str, ...], pass_field: str, pass_values: tuple[str, ...])`; `Task(id: str, role: str, brief: str, inputs: dict[str, str], programs: tuple[str, ...], tree: dict[str, str] | None, wall_seconds: int, oracle: Oracle, digest: str)`; `load_task(path: Path, supplied: dict[str, str]) -> Task`; `TaskError(ValueError)`.

A task file declares the inputs it needs by name; the CLI supplies their values, which are substituted into `brief`, `oracle.argv` and `tree` as `{name}`. `{trial}` is reserved and left for `run_trial`.

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pytest

from omnidriver_agents.task import TaskError, load_task

BASE = {
    "id": "t1", "role": "runner", "brief": "Run the case at {cases}. Write answer.json.",
    "inputs": ["cases"], "programs": ["openCARP"], "wall_seconds": 600,
    "oracle": {"argv": ["python3", "{task_dir}/oracle.py", "{trial}"], "pass_field": "status", "pass_values": ["passed"]},
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps(data))
    return path


def test_supplied_inputs_fill_the_brief_and_the_oracle(tmp_path):
    task = load_task(_write(tmp_path, BASE), {"cases": "/c"})
    assert task.brief == "Run the case at /c. Write answer.json."
    assert task.oracle.argv == ("python3", f"{tmp_path}/oracle.py", "{trial}")
    assert len(task.digest) == 64


def test_a_missing_input_is_refused_by_name(tmp_path):
    with pytest.raises(TaskError, match="cases"):
        load_task(_write(tmp_path, BASE), {})


def test_an_unknown_key_is_refused(tmp_path):
    with pytest.raises(TaskError, match="budget"):
        load_task(_write(tmp_path, {**BASE, "budget": 3}), {"cases": "/c"})


def test_an_unknown_role_is_refused(tmp_path):
    with pytest.raises(TaskError, match="role"):
        load_task(_write(tmp_path, {**BASE, "role": "pilot"}), {"cases": "/c"})
```

- [ ] **Step 2: Run; expect FAIL** (module missing). Run: `/tmp/od-agents/bin/python -m pytest packages/omnidriver-agents/tests/test_task.py -q`

- [ ] **Step 3: Implement `task.py`**

```python
"""A task an agent is given: the brief, the inputs it needs, and the oracle that judges it."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROLES = frozenset({"builder", "runner", "evaluator", "maintainer"})
_KEYS = {"id", "role", "brief", "inputs", "programs", "tree", "wall_seconds", "oracle"}
_FIELD = re.compile(r"\{(\w+)\}")


class TaskError(ValueError):
    """A task file that cannot be used as written."""


@dataclass(frozen=True)
class Oracle:
    argv: tuple[str, ...]
    pass_field: str
    pass_values: tuple[str, ...]


@dataclass(frozen=True)
class Task:
    id: str
    role: str
    brief: str
    inputs: dict[str, str]
    programs: tuple[str, ...]
    tree: dict[str, str] | None
    wall_seconds: int
    oracle: Oracle
    digest: str


def load_task(path: Path, supplied: dict[str, str]) -> Task:
    """Read a task file and fill its ``{name}`` fields from ``supplied``; ``{trial}`` stays for the trial."""
    raw = path.read_bytes()
    data = json.loads(raw)
    unknown = set(data) - _KEYS
    if unknown:
        raise TaskError(f"{path}: unknown keys {sorted(unknown)}")
    if data["role"] not in ROLES:
        raise TaskError(f"{path}: role {data['role']!r} is not one of {sorted(ROLES)}")
    missing = [name for name in data["inputs"] if name not in supplied]
    if missing:
        raise TaskError(f"{path}: inputs not supplied: {missing}")
    values = {**{n: supplied[n] for n in data["inputs"]}, "task_dir": str(path.parent)}

    # Only declared names are filled, so literal JSON braces in a brief survive.
    def fill(text: str) -> str:
        return _FIELD.sub(lambda m: values.get(m.group(1), m.group(0)), text)

    oracle = data["oracle"]
    return Task(
        id=data["id"], role=data["role"], brief=fill(data["brief"]),
        inputs={n: supplied[n] for n in data["inputs"]},
        programs=tuple(data.get("programs", ())),
        tree={k: fill(v) for k, v in data["tree"].items()} if data.get("tree") else None,
        wall_seconds=int(data["wall_seconds"]),
        oracle=Oracle(tuple(fill(a) for a in oracle["argv"]), oracle["pass_field"], tuple(oracle["pass_values"])),
        digest=hashlib.sha256(raw).hexdigest(),
    )
```

- [ ] **Step 4: Run; expect 4 passed.**
- [ ] **Step 5: Commit** — `feat(agents): task files with supplied inputs and an oracle`

---

### Task 3: Guidance, as provider-integration.md specifies

**Files:** Create `src/omnidriver_agents/guidance.py`, `tests/test_guidance.py`

**Interfaces:**
- Produces: `Guidance(text: str, files: tuple[tuple[str, str], ...])` (repo-relative path, SHA-256); `load_guidance(repo: Path, role: str) -> Guidance`; `GuidanceError(ValueError)`.

- [ ] **Step 1: Write the failing tests**

```python
import hashlib

import pytest

from omnidriver_agents.guidance import GuidanceError, load_guidance


def _repo(tmp_path, runner_required=("agent-handbook/runner.md",)):
    (tmp_path / "agent-handbook").mkdir()
    (tmp_path / "AGENTS.md").write_text("router\n")
    (tmp_path / "agent-handbook/runner.md").write_text("runner\n")
    required = "\n".join(f"      - {p}" for p in runner_required)
    (tmp_path / "agent-handbook/guidance-manifest.yaml").write_text(
        f"version: 1\ncommon:\n  - AGENTS.md\nroles:\n  runner:\n    required:\n{required}\n"
    )
    return tmp_path


def test_common_then_required_files_with_their_hashes(tmp_path):
    guidance = load_guidance(_repo(tmp_path), "runner")
    assert [p for p, _ in guidance.files] == ["AGENTS.md", "agent-handbook/runner.md"]
    assert guidance.files[0][1] == hashlib.sha256(b"router\n").hexdigest()
    assert guidance.text.index("router") < guidance.text.index("runner")


def test_a_missing_listed_file_fails(tmp_path):
    with pytest.raises(GuidanceError, match="nope.md"):
        load_guidance(_repo(tmp_path, ("agent-handbook/nope.md",)), "runner")


def test_an_unknown_role_fails(tmp_path):
    with pytest.raises(GuidanceError, match="pilot"):
        load_guidance(_repo(tmp_path), "pilot")
```

- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement `guidance.py`**

```python
"""The guidance an agent receives for a role, resolved from the repository's manifest with each file's hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST = "agent-handbook/guidance-manifest.yaml"


class GuidanceError(ValueError):
    """The manifest names a role or a file that does not exist."""


@dataclass(frozen=True)
class Guidance:
    text: str
    files: tuple[tuple[str, str], ...]


def load_guidance(repo: Path, role: str) -> Guidance:
    """The manifest's ``common`` files, then the role's ``required`` ones, concatenated, each hashed."""
    manifest = yaml.safe_load((repo / MANIFEST).read_text())
    if role not in manifest["roles"]:
        raise GuidanceError(f"{MANIFEST} has no role {role!r}")
    paths = [*manifest["common"], *manifest["roles"][role]["required"]]
    parts, files = [], []
    for relpath in paths:
        path = repo / relpath
        if not path.is_file():
            raise GuidanceError(f"{MANIFEST} lists {relpath}, which does not exist")
        data = path.read_bytes()
        files.append((relpath, hashlib.sha256(data).hexdigest()))
        parts.append(f"<file path=\"{relpath}\">\n{data.decode()}\n</file>")
    return Guidance(text="\n\n".join(parts), files=tuple(files))
```

- [ ] **Step 4: Run; expect 3 passed.** Also run against the real repo: `/tmp/od-agents/bin/python -c "from pathlib import Path; from omnidriver_agents.guidance import load_guidance; print(load_guidance(Path('.'), 'runner').files)"` — expect `AGENTS.md` and `agent-handbook/runner.md`.
- [ ] **Step 5: Commit** — `feat(agents): inject a role's guidance and record its hashes`

---

### Task 4: Native tree export and digest

**Files:** Create `src/omnidriver_agents/tree.py`, `tests/test_tree.py`

**Interfaces:**
- Produces: `export_tree(git_dir: Path, ref: str, dest: Path) -> str` (returns the commit hash); `digest_tree(root: Path) -> str` (SHA-256 over sorted relative paths and file bytes; symlinks by target text).

- [ ] **Step 1: Write the failing tests**

```python
import subprocess

from omnidriver_agents.tree import digest_tree, export_tree


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_export_is_the_committed_tree_only(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init", "-q")
    (src / "a.txt").write_text("a")
    _git(src, "add", "a.txt")
    _git(src, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a")
    (src / "untracked.txt").write_text("u")
    commit = export_tree(src, "HEAD", tmp_path / "out")
    assert len(commit) == 40
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.txt"]


def test_digest_changes_with_content_and_not_with_mtime(tmp_path):
    (tmp_path / "f").write_text("x")
    before = digest_tree(tmp_path)
    (tmp_path / "f").touch()
    assert digest_tree(tmp_path) == before
    (tmp_path / "f").write_text("y")
    assert digest_tree(tmp_path) != before
```

- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement `tree.py`**

```python
"""A trial's native tree: exported from git so it holds only committed files, and digested before and after."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


def export_tree(git_dir: Path, ref: str, dest: Path) -> str:
    """Write ``git archive <ref>`` of ``git_dir`` into ``dest``; return the commit it resolved to."""
    commit = subprocess.run(["git", "-C", str(git_dir), "rev-parse", f"{ref}^{{commit}}"],
                            check=True, capture_output=True, text=True).stdout.strip()
    archive = subprocess.run(["git", "-C", str(git_dir), "archive", commit], check=True, capture_output=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    return commit


def digest_tree(root: Path) -> str:
    """SHA-256 over every path under ``root`` and its content; times are ignored."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relpath = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            digest.update(b"L" + relpath + b"\0" + str(path.readlink()).encode() + b"\0")
        elif path.is_file():
            digest.update(b"F" + relpath + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
```

- [ ] **Step 4: Run; expect 2 passed.**
- [ ] **Step 5: Commit** — `feat(agents): export a native tree from git and digest it`

---

### Task 5: Launch shims

**Files:** Create `src/omnidriver_agents/shims.py`, `tests/test_shims.py`

**Interfaces:**
- Produces: `write_shims(bin_dir: Path, programs: tuple[str, ...], log: Path) -> None`. Each shim is an executable Python script (shebang = the harness's `sys.executable`) that finds the real program on `PATH` after removing `bin_dir`, runs it with the same argv, stdin, stdout and stderr, appends `{"program", "argv", "cwd", "exit_code", "seconds"}` as one JSON line to `log`, and exits with the program's exit code. A program not found is logged with `exit_code: 127`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import os
import subprocess

from omnidriver_agents.shims import write_shims


def test_a_shim_runs_the_real_program_and_logs_it(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "solver").write_text("#!/bin/sh\necho ran \"$@\"\nexit 3\n")
    (real / "solver").chmod(0o755)
    shims = tmp_path / "shims"
    log = tmp_path / "launches.jsonl"
    write_shims(shims, ("solver",), log)
    env = {**os.environ, "PATH": f"{shims}:{real}:/usr/bin:/bin"}
    result = subprocess.run(["solver", "-x", "1"], env=env, capture_output=True, text=True)
    assert result.returncode == 3
    assert result.stdout == "ran -x 1\n"
    entry = json.loads(log.read_text())
    assert entry["program"] == "solver" and entry["argv"] == ["-x", "1"] and entry["exit_code"] == 3


def test_a_missing_program_is_logged_as_127(tmp_path):
    shims, log = tmp_path / "shims", tmp_path / "launches.jsonl"
    write_shims(shims, ("ghost",), log)
    env = {**os.environ, "PATH": f"{shims}:/usr/bin:/bin"}
    assert subprocess.run(["ghost"], env=env, capture_output=True).returncode == 127
    assert json.loads(log.read_text())["exit_code"] == 127
```

- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement `shims.py`**

```python
"""Wrappers first on a trial's PATH that log every launch of a solver program, in both conditions alike."""

from __future__ import annotations

import sys
from pathlib import Path

_SHIM = '''#!{python}
import json, os, shutil, subprocess, sys, time
bin_dir, log = {bin_dir!r}, {log!r}
path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if os.path.realpath(p) != os.path.realpath(bin_dir))
real = shutil.which({program!r}, path=path)
start = time.monotonic()
code = 127 if real is None else subprocess.call([real, *sys.argv[1:]])
with open(log, "a") as f:
    f.write(json.dumps({{"program": {program!r}, "argv": sys.argv[1:], "cwd": os.getcwd(), "exit_code": code, "seconds": round(time.monotonic() - start, 3)}}) + "\\n")
sys.exit(code)
'''


def write_shims(bin_dir: Path, programs: tuple[str, ...], log: Path) -> None:
    """Write one logging shim per program into ``bin_dir``."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for program in programs:
        shim = bin_dir / program
        shim.write_text(_SHIM.format(python=sys.executable, bin_dir=str(bin_dir), log=str(log), program=program))
        shim.chmod(0o755)
```

- [ ] **Step 4: Run; expect 2 passed.**
- [ ] **Step 5: Commit** — `feat(agents): shims that log every solver launch`

---

### Task 6: Adapters: the protocol, Claude Code, and the fake

**Files:** Create `src/omnidriver_agents/adapters/__init__.py`, `src/omnidriver_agents/adapters/claude_code.py`, `tests/conftest.py`, `tests/test_claude_code.py`, `tests/fixtures/stream.jsonl`

**Interfaces:**
- Produces: `AdapterResult(final_text: str, transcript: list[dict], turns: int, cost_usd: float | None, usage: dict, is_error: bool, timed_out: bool)`; `Adapter` protocol with `name: str`, `version() -> str`, `run(prompt: str, system: str | None, cwd: Path, env: dict[str, str], wall_seconds: int) -> AdapterResult`; `ClaudeCodeAdapter(model: str, executable: Path)`; `parse_stream(lines: Iterable[str]) -> AdapterResult`; `FakeAdapter` in `tests/conftest.py` (fixture `fake_adapter`).

`stream-json` shape, observed with `claude -p ... --output-format stream-json --verbose` on 2026-10-09: one JSON object per line; `type` is `system` (subtypes `init`, `hook_started`, `hook_response`), `assistant`, `user` (tool results), or `result`. The `result` line carries `num_turns`, `total_cost_usd`, `usage`, `is_error`, `result` (final text). `--verbose` is required with `stream-json` in `-p` mode.

- [ ] **Step 1: Write the fixture** `tests/fixtures/stream.jsonl` (three lines):

```
{"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001", "plugins": [], "cwd": "/t"}
{"type": "user", "message": {"content": [{"type": "tool_result", "content": "{\"status\": \"failed\", \"error\": \"ScratchRootNotSupplied\"}"}]}}
{"type": "result", "subtype": "success", "is_error": false, "num_turns": 4, "total_cost_usd": 0.0123, "usage": {"input_tokens": 10, "output_tokens": 20}, "result": "done"}
```

- [ ] **Step 2: Write the failing tests** `tests/test_claude_code.py`:

```python
from pathlib import Path

from omnidriver_agents.adapters.claude_code import ClaudeCodeAdapter, parse_stream

FIXTURE = Path(__file__).parent / "fixtures/stream.jsonl"


def test_the_result_line_gives_turns_cost_usage_and_text():
    result = parse_stream(FIXTURE.read_text().splitlines())
    assert (result.turns, result.cost_usd, result.final_text, result.is_error) == (4, 0.0123, "done", False)
    assert result.usage["output_tokens"] == 20
    assert len(result.transcript) == 3


def test_a_stream_without_a_result_line_is_an_error():
    result = parse_stream(FIXTURE.read_text().splitlines()[:2])
    assert result.is_error and result.turns == 0


def test_the_command_is_headless_with_the_model_and_the_guidance():
    adapter = ClaudeCodeAdapter(model="sonnet", executable=Path("/x/claude"))
    argv = adapter.command("do it", "GUIDE")
    assert argv[:2] == ["/x/claude", "-p"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv and "--no-session-persistence" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == "GUIDE"
    assert "--append-system-prompt" not in adapter.command("do it", None)
```

- [ ] **Step 3: Run; expect FAIL.**
- [ ] **Step 4: Implement** `adapters/__init__.py`:

```python
"""What every agent adapter returns, and the one method it implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class AdapterResult:
    final_text: str
    transcript: list[dict]
    turns: int
    cost_usd: float | None
    usage: dict = field(default_factory=dict)
    is_error: bool = False
    timed_out: bool = False


class Adapter(Protocol):
    name: str

    def version(self) -> str: ...

    def run(self, prompt: str, system: str | None, cwd: Path, env: dict[str, str], wall_seconds: int) -> AdapterResult: ...
```

`adapters/claude_code.py`:

```python
"""Claude Code, run headless with ``claude -p`` and read from its ``stream-json`` output."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from . import AdapterResult


def parse_stream(lines: Iterable[str]) -> AdapterResult:
    """One ``stream-json`` transcript; the ``result`` line carries turns, cost, usage and the final text."""
    transcript = [json.loads(line) for line in lines if line.strip()]
    final = next((e for e in reversed(transcript) if e.get("type") == "result"), None)
    if final is None:
        return AdapterResult(final_text="", transcript=transcript, turns=0, cost_usd=None, is_error=True)
    return AdapterResult(
        final_text=final.get("result", ""), transcript=transcript, turns=final.get("num_turns", 0),
        cost_usd=final.get("total_cost_usd"), usage=final.get("usage", {}), is_error=bool(final.get("is_error")),
    )


class ClaudeCodeAdapter:
    def __init__(self, model: str, executable: Path):
        self.model, self.executable = model, executable
        self.name = f"claude-code:{model}"

    def command(self, prompt: str, system: str | None) -> list[str]:
        argv = [str(self.executable), "-p", prompt, "--model", self.model, "--output-format", "stream-json",
                "--verbose", "--no-session-persistence", "--permission-mode", "bypassPermissions"]
        if system is not None:
            argv += ["--append-system-prompt", system]
        return argv

    def version(self) -> str:
        return subprocess.run([str(self.executable), "--version"], capture_output=True, text=True).stdout.strip()

    def run(self, prompt: str, system: str | None, cwd: Path, env: dict[str, str], wall_seconds: int) -> AdapterResult:
        try:
            done = subprocess.run(self.command(prompt, system), cwd=cwd, env=env, capture_output=True,
                                  text=True, timeout=wall_seconds)
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            result = parse_stream(out.splitlines())
            result.timed_out, result.is_error = True, True
            return result
        return parse_stream(done.stdout.splitlines())
```

`tests/conftest.py`:

```python
import json
from pathlib import Path

import pytest

from omnidriver_agents.adapters import AdapterResult


class FakeAdapter:
    """Plays a script: each step is a shell command run in the trial folder, then a final answer."""

    name = "fake"

    def __init__(self, commands=(), answer=None):
        self.commands, self.answer, self.calls = commands, answer, []

    def version(self):
        return "fake-1"

    def run(self, prompt, system, cwd, env, wall_seconds):
        import subprocess
        self.calls.append({"prompt": prompt, "system": system, "env": env})
        transcript = []
        for command in self.commands:
            out = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
            transcript.append({"type": "user", "message": {"content": [{"type": "tool_result", "content": out.stdout}]}})
        if self.answer is not None:
            (Path(cwd) / "answer.json").write_text(json.dumps(self.answer))
        return AdapterResult(final_text="done", transcript=transcript, turns=len(self.commands) + 1, cost_usd=0.0)


@pytest.fixture
def fake_adapter():
    return FakeAdapter
```

- [ ] **Step 5: Run; expect 3 passed.**
- [ ] **Step 6: Commit** — `feat(agents): the adapter protocol and a Claude Code adapter`

---

### Task 7: A trial and its record

**Files:** Create `src/omnidriver_agents/trial.py`, `tests/test_trial.py`

**Interfaces:**
- Consumes: `Task`, `Guidance`/`load_guidance`, `export_tree`, `digest_tree`, `write_shims`, `Adapter`, `AdapterResult`.
- Produces: `TrialSetup(output: Path, condition: str, omnid_repo: Path, omnidriver_bin: Path, solver_path: tuple[Path, ...], extra_env: dict[str, str])`; `run_trial(task: Task, adapter: Adapter, setup: TrialSetup, index: int) -> dict` (the record, also written to `<output>/<task.id>/<adapter.name>/<condition>/<index>/task_record.json`, beside `transcript.jsonl` and `launches.jsonl`). The trial folder is `.../<index>/work`, which is `{trial}` in the oracle's argv.

PATH in the trial is exactly: the shim folder, then `solver_path`, then the folder holding `omnidriver_bin` **only** for `omnid`, then `/usr/bin:/bin`. HOME is the user's, so that CLI login state is found; `extra_env` (e.g. `CLAUDE_CONFIG_DIR`, `DYLD_LIBRARY_PATH`) is supplied. Refusals are counted as tool results containing `"status": "failed"`. The oracle runs after the agent, with PATH including `omnidriver_bin`'s folder in both conditions; its stdout must be JSON.

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

from omnidriver_agents.task import Oracle, Task
from omnidriver_agents.trial import TrialSetup, run_trial

ORACLE = """import json, sys
answer = json.load(open(sys.argv[1] + "/answer.json"))
print(json.dumps({"status": "passed" if answer.get("P8") == 42 else "failed"}))
"""


def _task(tmp_path):
    (tmp_path / "oracle.py").write_text(ORACLE)
    return Task(id="t", role="runner", brief="go", inputs={}, programs=("solver",), tree=None, wall_seconds=60,
                oracle=Oracle((sys.executable, str(tmp_path / "oracle.py"), "{trial}"), "status", ("passed",)),
                digest="d" * 64)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "agent-handbook").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("router")
    (repo / "agent-handbook/runner.md").write_text("runner")
    (repo / "agent-handbook/guidance-manifest.yaml").write_text(
        "version: 1\ncommon: [AGENTS.md]\nroles:\n  runner:\n    required: [agent-handbook/runner.md]\n")
    return repo


def _setup(tmp_path, condition):
    omnid_bin = tmp_path / "omnid-bin"
    omnid_bin.mkdir(exist_ok=True)
    (omnid_bin / "omnidriver").write_text("#!/bin/sh\necho '{\"status\": \"failed\", \"error\": \"x\"}'\n")
    (omnid_bin / "omnidriver").chmod(0o755)
    return TrialSetup(output=tmp_path / "out", condition=condition, omnid_repo=_repo(tmp_path),
                      omnidriver_bin=omnid_bin / "omnidriver", solver_path=(), extra_env={})


def test_omnid_gets_guidance_and_omnidriver_and_the_oracle_decides(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["omnidriver plan"], answer={"P8": 42})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "omnid"), 0)
    assert "router" in adapter.calls[0]["system"]
    assert [p for p, _ in record["guidance"]] == ["AGENTS.md", "agent-handbook/runner.md"]
    assert record["refusals"] == 1 and record["success"] is True
    folder = tmp_path / "out/t/fake/omnid/0"
    assert json.loads((folder / "task_record.json").read_text()) == record
    assert (folder / "transcript.jsonl").exists()


def test_bare_gets_no_guidance_and_no_omnidriver(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["command -v omnidriver || echo absent"], answer={"P8": 1})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "bare"), 0)
    assert adapter.calls[0]["system"] is None
    assert "omnid-bin" not in adapter.calls[0]["env"]["PATH"]
    assert record["guidance"] == [] and record["success"] is False
```

- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement `trial.py`**

```python
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
```

- [ ] **Step 4: Run; expect 2 passed.** Then the whole package: `/tmp/od-agents/bin/python -m pytest packages/omnidriver-agents/tests -q` — 0 failed.
- [ ] **Step 5: Commit** — `feat(agents): a trial writes one record judged by the task's oracle`

---

### Task 8: Summary and the CLI

**Files:** Create `src/omnidriver_agents/summary.py`, `src/omnidriver_agents/cli.py`, `tests/test_summary.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_task`, `run_trial`, `TrialSetup`, `ClaudeCodeAdapter`.
- Produces: `summarize(output: Path) -> list[dict]` (one row per task × adapter × condition: `trials`, `successes`, median `seconds`, median `turns`, total `cost_usd`, mean `launches`, mean `refusals`, `tree_changed` count); `main(argv: list[str] | None = None) -> int`.

CLI: `omnidriver-agents run --task <task.json> --input name=value ... --model <m> [--model <m> ...] --condition omnid --condition bare --repeats N --output <dir> --omnid-repo <path> --omnidriver <path to omnidriver executable> --claude <path to claude> [--solver-path <dir> ...] [--env NAME=VALUE ...]` and `omnidriver-agents summarize <dir>` (prints the rows as JSON). Every required path is supplied; none has a default.

- [ ] **Step 1: Write the failing tests**

`tests/test_summary.py`:

```python
import json

from omnidriver_agents.summary import summarize


def test_one_row_per_task_adapter_condition(tmp_path):
    for i, (ok, s) in enumerate([(True, 10), (False, 30), (True, 20)]):
        folder = tmp_path / "t/fake/omnid" / str(i)
        folder.mkdir(parents=True)
        (folder / "task_record.json").write_text(json.dumps({
            "task": "t", "adapter": "fake", "condition": "omnid", "success": ok, "seconds": s, "turns": 2,
            "cost_usd": 0.5, "launches": 1, "refusals": 0, "tree_before": "a", "tree_after": "a"}))
    [row] = summarize(tmp_path)
    assert (row["trials"], row["successes"], row["median_seconds"], row["cost_usd"]) == (3, 2, 20, 1.5)
    assert row["tree_changed"] == 0
```

`tests/test_cli.py`:

```python
import pytest

from omnidriver_agents.cli import main


def test_run_requires_every_path(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--task", "t.json", "--model", "haiku", "--condition", "omnid", "--repeats", "1"])
    assert exc.value.code == 2
    assert "--output" in capsys.readouterr().err
```

- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement** `summary.py`:

```python
"""One table over a results folder: per task, adapter and condition."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(output: Path) -> list[dict]:
    """Group every ``task_record.json`` under ``output`` and reduce each group to one row."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for path in sorted(output.rglob("task_record.json")):
        record = json.loads(path.read_text())
        groups[(record["task"], record["adapter"], record["condition"])].append(record)
    rows = []
    for (task, adapter, condition), records in sorted(groups.items()):
        rows.append({
            "task": task, "adapter": adapter, "condition": condition, "trials": len(records),
            "successes": sum(r["success"] for r in records),
            "median_seconds": statistics.median(r["seconds"] for r in records),
            "median_turns": statistics.median(r["turns"] for r in records),
            "cost_usd": round(sum(r["cost_usd"] or 0 for r in records), 4),
            "mean_launches": statistics.mean(r["launches"] for r in records),
            "mean_refusals": statistics.mean(r["refusals"] for r in records),
            "tree_changed": sum(r.get("tree_before") != r.get("tree_after") for r in records),
        })
    return rows
```

`cli.py`:

```python
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
```

- [ ] **Step 4: Run all package tests; expect 0 failed.** `/tmp/od-agents/bin/python -m pytest packages/omnidriver-agents/tests -q`
- [ ] **Step 5: Commit** — `feat(agents): the run and summarize commands`

---

### Task 9: Isolation probe (needs the owner once) and the first task

**Files:** Create `packages/omnidriver-agents/tasks/nversion-opencarp/task.json`, `oracle.py`, `README.md`

This task touches real models and a real solver, so it is run by hand, not by pytest.

- [ ] **Step 1 (owner): log the CLI in under a dedicated home.** The CLI at `~/.local/bin/claude` is not logged in (a probe on 2026-10-09 returned `authentication_failed`). Run once, in a terminal, with `<agent-home>` a folder outside every repository (for example `~/omnid-agents-home`):

```bash
HOME=<agent-home> claude
```

and run `/login`. `<agent-home>/.claude` holds no memory, plugins, hooks or `CLAUDE.md`. Also make a Python outside omniD's venvs that cannot `import omnidriver`, for `--agent-python`.

- [ ] **Step 2: Isolation probe.** In a folder outside every repository, run:

```bash
HOME=<agent-home> claude -p "List every instruction, memory, plugin, skill and hook you were given beyond this message, verbatim, or say none." --model haiku --output-format stream-json --verbose --no-session-persistence > probe.jsonl
```

Pass when the `init` line's `plugins` is `[]`, no `hook_*` lines appear, and the answer names no omniD memory or `CLAUDE.md`. Record the result in the README. If it fails, stop and report; no trial counts until it passes.

- [ ] **Step 3: Freeze the reference.** One omniD run of openCARP's `niedererNVersion` at its coarsest `dx`, using the A-runs' scratch evidence in `~/omnid-runs/2026-10-09` if it holds one, otherwise:

```bash
omnidriver run --plugin opencarp --cases-root /usr/local/lib/opencarp/share/tutorials --entry niedererNVersion --scratch-dir ~/omnid-runs/2026-10-09/reference
```

Read P1 and P8 activation times (ms) from its LAT output and write them into `<refs.json>`, a JSON object of strings (`{"P1_REF": "...", "P8_REF": "..."}`) passed as `--oracle-env-file`, so the agent never sees them; `oracle.py` reads them from its environment.

- [ ] **Step 4: Write `oracle.py`** (condition-neutral: it grades the reported numbers, not omniD artifacts):

```python
"""Grade answer.json's P1 and P8 activation times (ms) against the frozen reference, within a tolerance."""

import json
import os
import sys
from pathlib import Path

trial, tol = sys.argv[1], float(sys.argv[2])
p1_ref, p8_ref = float(os.environ["P1_REF"]), float(os.environ["P8_REF"])
try:
    answer = json.loads((Path(trial) / "answer.json").read_text())
    p1, p8 = float(answer["P1"]), float(answer["P8"])
except (OSError, KeyError, ValueError, TypeError) as exc:
    print(json.dumps({"status": "failed", "reason": f"no usable answer.json: {exc}"}))
    sys.exit(0)
ok = abs(p1 - p1_ref) <= tol and abs(p8 - p8_ref) <= tol
print(json.dumps({"status": "passed" if ok else "failed", "P1": p1, "P8": p8, "P1_ref": p1_ref, "P8_ref": p8_ref, "tolerance_ms": tol}))
```

- [ ] **Step 5: Write `task.json`** (the references are not in it; tolerance 1 ms):

```json
{
  "id": "nversion-opencarp",
  "role": "runner",
  "brief": "Using openCARP (tutorials at {tutorials}), run the Niederer 2011 N-version benchmark (tutorial 02_EP_tissue/03E_study_resolution) at a spatial resolution of {dx_um} um and its default time step. Use {trial}/scratch for any scratch space. When done, write {trial}/answer.json as {\"P1\": <activation time at P1 in ms>, \"P8\": <activation time at P8 in ms>}.",
  "inputs": ["tutorials", "dx_um"],
  "programs": ["openCARP", "mesher", "mpirun"],
  "wall_seconds": 1800,
  "oracle": {"argv": ["python3", "{task_dir}/oracle.py", "{trial}", "1.0"], "pass_field": "status", "pass_values": ["passed"]}
}
```

- [ ] **Step 6: A one-trial smoke run** with Haiku, `omnid` only, `--repeats 1`, `--agent-home <agent-home> --agent-python <python> --env DYLD_LIBRARY_PATH=/opt/homebrew/lib --oracle-env-file <refs.json>`, `--solver-path /usr/local/bin`. Check the record is complete. Then the experiment: `--model opus --model sonnet --model haiku --condition omnid --condition bare --repeats 3`, and `omnidriver-agents summarize`.
- [ ] **Step 7: README** — the task, the isolation probe result, the commands as run, and the summary table. Commit — `feat(agents): the first task, N-version on openCARP`
