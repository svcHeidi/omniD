"""MPI launchers, solver-neutral: how a step is wrapped in one, how a wrapped
step is read back, and what process count a parallel run may use. Whether a
launcher belongs to the MPI a solver was built against is the solver's own
check."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

LAUNCHERS = frozenset({"mpirun", "mpiexec", "orterun"})
_RANK_FLAGS = ("-np", "-n", "--np")


def wrap(step: Mapping[str, Any], n: int, launcher: str = "mpirun") -> dict[str, Any]:
    """``step`` run as ``<launcher> -np n <command> <args>``, keeping its id, inputs and outputs."""
    return {**step, "command": launcher, "args": ["-np", str(n), step["command"], *step.get("args", ())]}


def ranks(args: Iterable[str]) -> int | None:
    """The process count a launcher's ``args`` ask for, or ``None``."""
    args = list(args)
    for flag in _RANK_FLAGS:
        if flag in args and args.index(flag) + 1 < len(args):
            try:
                return int(args[args.index(flag) + 1])
            except ValueError:
                return None
    return None


def program(args: Iterable[str]) -> str | None:
    """The program a launcher's ``args`` run, or ``None`` when they name only launcher flags."""
    args = list(args)
    index = 0
    while index < len(args):
        token = args[index]
        if token in _RANK_FLAGS:
            index += 2
        elif token.startswith("-"):
            index += 1
        else:
            return token
    return None


def requested(request: Any) -> int | None:
    """The count a ``parallel`` request states: ``None`` for ``true`` (the
    solver's own source decides), else the positive integer."""
    if request is True:
        return None
    if type(request) is int and request >= 1:
        return request
    raise ValueError(f"a parallel request is true or a positive process count, got {request!r}")


def agree(n: int | None, allocation: Any, *, stated_by: str = "the request") -> int:
    """The process count of a parallel run: ``n`` when ``stated_by`` states
    one, else the scheduler's ``allocation``. Neither, or two that disagree,
    is refused: an allocation is never overridden."""
    if allocation is None:
        if n is None:
            raise ValueError(
                "no process count is stated and no scheduler allocation is ambient "
                "(SLURM_NTASKS); supply the count with the request: parallel N, or --parallel N"
            )
        return n
    if n is not None and n != allocation.ranks:
        raise ValueError(
            f"{stated_by} gives {n} processes, but the scheduler allocated "
            f"{allocation.variable}={allocation.ranks}; use {allocation.ranks}, or "
            "parallel true where the allocation decides"
        )
    return allocation.ranks


def identity(launcher: str, env: Mapping[str, str]) -> dict[str, Any]:
    """The launcher ``launcher`` resolves to on ``env``'s PATH: its path, real
    path and the first lines ``--version`` prints (Open MPI names itself on
    the first, MPICH's hydra on the second)."""
    path = shutil.which(launcher, path=env.get("PATH"))
    found: dict[str, Any] = {"command": launcher, "path": path, "real_path": None, "version": None}
    if path is None:
        return found
    found["real_path"] = str(Path(path).resolve())
    try:
        completed = subprocess.run(
            (path, "--version"), capture_output=True, text=True, env=dict(env), timeout=30, check=False,
        )
        lines = [line.strip() for line in (completed.stdout + completed.stderr).splitlines() if line.strip()]
        found["version"] = lines[:3]
    except (OSError, subprocess.TimeoutExpired) as exc:
        found["version"] = [f"--version failed: {exc}"]
    return found
