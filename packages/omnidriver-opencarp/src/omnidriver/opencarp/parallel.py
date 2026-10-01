"""openCARP in parallel: the solve under an MPI launcher (``mpirun -np N openCARP ...``); PETSc partitions the mesh itself and the outputs keep the serial layout, node order and location.

There is no decomposition dictionary, so N comes from the scheduler's allocation or an explicit request (never both disagreeing, nor neither); the launcher must belong to the MPI openCARP was built against, or a parallel run silently is not one -- see docs/solver-learning/opencarp.md and :func:`launcher_diagnostics`."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from omnidriver.core.planning_types import StrictDiagnostic
from omnidriver.core.runtime import mpi

SOLVER = "openCARP"
#: ``mpirun -np 2 openCARP +Default`` initialises MPI and prints the build
#: header once per MPI world, then stops for want of a mesh.
_PROBE_RANKS = 2
_HEADER_MARK = "GIT tag"


def parallel_steps(step: Mapping[str, Any], *, request: Any, read_value: Any, allocation: Any) -> list[dict]:
    """openCARP's ``get_parallel_steps``: the solve step under ``mpirun -np
    N``. ``request`` is ``True`` (N from the scheduler's allocation) or a
    positive integer N."""
    del read_value      # openCARP's case states no process count
    return [mpi.wrap(step, mpi.agree(mpi.requested(request), allocation))]


def launcher_diagnostics(workflow_dag: Mapping[str, Any], env: Mapping[str, str]) -> tuple[StrictDiagnostic, ...]:
    """For each launcher a step runs openCARP under, whether it starts ONE
    MPI world of openCARP processes: ``<launcher> -np 2 openCARP +Default``
    in a scratch directory must print the build header once. The header
    itself is never echoed."""
    launchers = sorted({
        step["command"] for step in (workflow_dag or {}).get("steps", ())
        if step.get("command") != SOLVER and SOLVER in (step.get("args") or ())
    })
    path = env.get("PATH", "")
    diagnostics = []
    for launcher in launchers:
        found = shutil.which(launcher, path=path)
        if found is None or shutil.which(SOLVER, path=path) is None:
            continue    # reported as a missing command by the caller
        with tempfile.TemporaryDirectory(prefix="opencarp-launcher-probe-") as scratch:
            proc = subprocess.run(
                [found, "-np", str(_PROBE_RANKS), SOLVER, "+Default"], cwd=scratch,
                capture_output=True, text=True, env=dict(env), timeout=120,
            )
        headers = (proc.stdout + proc.stderr).count(_HEADER_MARK)
        if headers == 1:
            continue
        if headers == 0:
            tail = [line for line in (proc.stdout + proc.stderr).splitlines() if "://" not in line][-6:]
            message = (
                f"{launcher!r} ({found}) could not start {_PROBE_RANKS} openCARP processes: "
                + " | ".join(tail)[-600:]
            )
        else:
            message = (
                f"{launcher!r} ({found}) started {headers} separate one-process openCARP runs, not "
                f"one {_PROBE_RANKS}-process run: it is not the launcher of the MPI openCARP was "
                "built against, and a parallel run would solve the whole problem once per process "
                "into one output directory (evidence I2). Put that MPI's launcher first on PATH"
            )
        diagnostics.append(StrictDiagnostic(level="error", code="opencarp_mpi_launcher_mismatch", message=message))
    return tuple(diagnostics)
