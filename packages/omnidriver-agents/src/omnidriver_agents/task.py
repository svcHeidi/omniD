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
