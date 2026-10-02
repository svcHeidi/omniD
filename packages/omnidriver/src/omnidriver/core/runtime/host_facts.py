"""Where a workflow step ran: ambient facts, recorded, never interpreted.

Machine/OS/CPU identity, ambient scheduler/threading variables, declared
stack variables, and MPI launcher identity when applicable. Nothing here is
supplied or defaulted: an absent fact is absent.
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import mpi

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
    if command in mpi.LAUNCHERS:
        facts["launcher"] = {**mpi.identity(command, env), "ranks": mpi.ranks(args)}
    return facts
