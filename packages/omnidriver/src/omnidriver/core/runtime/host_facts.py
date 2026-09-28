"""Where a workflow step ran: ambient facts, recorded, never interpreted.

Each step's state (``workflow_state.json``, ``steps[].host``) carries the
machine's name, OS, CPU and core count, the scheduler and threading variables
that are set (read from the declared prefixes below, the same ambient kind
``record_execution.SCHEDULER_ALLOCATION_VARIABLES`` reads), the values of the
stack's own declared environment variables (``environment.supplied`` in each
provider's manifest), and, for a step run under an MPI launcher, that
launcher's path, version and rank count. Nothing here is supplied or
defaulted: an absent fact is absent.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from .workflow import _MPI_LAUNCHERS

#: Where ambient allocation and threading facts are read: every variable
#: whose name starts with one of these.
AMBIENT_VARIABLE_PREFIXES = ("SLURM_", "OMP_", "OPENBLAS_", "MKL_")


@cache
def _cpu_model() -> str | None:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ("sysctl", "-n", "machdep.cpu.brand_string"),
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout.strip()
            return out or None
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.is_file():
            for line in cpuinfo.read_text(errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def launcher_identity(command: str, env: Mapping[str, str]) -> dict[str, Any]:
    """The launcher ``command`` resolves to on ``env``'s PATH: its path, real
    path and the first lines ``--version`` prints (Open MPI names itself on
    the first, MPICH's hydra on the second)."""
    path = shutil.which(command, path=env.get("PATH"))
    identity: dict[str, Any] = {"command": command, "path": path, "real_path": None, "version": None}
    if path is None:
        return identity
    identity["real_path"] = str(Path(path).resolve())
    try:
        completed = subprocess.run(
            (path, "--version"), capture_output=True, text=True, env=dict(env), timeout=30, check=False,
        )
        lines = [line.strip() for line in (completed.stdout + completed.stderr).splitlines() if line.strip()]
        identity["version"] = lines[:3]
    except (OSError, subprocess.TimeoutExpired) as exc:
        identity["version"] = [f"--version failed: {exc}"]
    return identity


def _ranks(args: Iterable[str]) -> int | None:
    args = list(args)
    for flag in ("-np", "-n", "--np"):
        if flag in args and args.index(flag) + 1 < len(args):
            try:
                return int(args[args.index(flag) + 1])
            except ValueError:
                return None
    return None


def host_facts(
    command: str, args: Iterable[str], env: Mapping[str, str] | None,
    *, declared_variables: Iterable[str] = (),
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    facts: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "ambient": {
            name: value for name, value in sorted(env.items())
            if name.startswith(AMBIENT_VARIABLE_PREFIXES)
        },
        "declared": {name: env[name] for name in declared_variables if name in env},
    }
    if command in _MPI_LAUNCHERS:
        facts["launcher"] = {**launcher_identity(command, env), "ranks": _ranks(args)}
    return facts
