"""Preflight: a record's runner must start under the python3 of TorchCor's venv.

Nothing is searched for: the venv's bin is supplied (TORCHCOR_BIN) and goes
first on PATH."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.runtime.planned_programs import program_diagnostics

SOLVER_COMMANDS = frozenset({"python3"})
BIN_VARIABLE = "TORCHCOR_BIN"


def torchcor_environment_diagnostics(
    workflow_dag: Mapping[str, Any], env: Mapping[str, str], driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    commands = sorted({step["command"] for step in (workflow_dag or {}).get("steps", ()) if step.get("command")})
    if not commands:
        return ()
    named = ", ".join(map(repr, commands))
    venv_bin = env.get(BIN_VARIABLE)
    python = shutil.which("python3", path=env.get("PATH", ""))
    diagnostics = list(program_diagnostics(workflow_dag, env, driver_context))
    # The shell `omnidriver env` prints puts TORCHCOR_BIN on PATH without
    # exporting it, so only a supplied value can be compared.
    if python is not None and venv_bin and Path(python).parent.resolve() != Path(venv_bin).expanduser().resolve():
        diagnostics.append(diagnostic(
            "error", "torchcor_python_not_torchcors",
            f"{named} would run under {python}, not the python3 in {BIN_VARIABLE}={venv_bin}; "
            f"put {BIN_VARIABLE} first on PATH (omnidriver env --plugin torchcor prints the prefix)",
            source="environment",
        ))
    return tuple(diagnostics)
