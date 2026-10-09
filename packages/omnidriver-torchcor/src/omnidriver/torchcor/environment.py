"""Preflight: a record's runner must start under the python3 of TorchCor's venv.

Nothing is searched for: the venv's bin is supplied (TORCHCOR_BIN) and goes
first on PATH."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .catalog import REPOSITORY_VARIABLE

SOLVER_COMMANDS = frozenset({"python3"})
BIN_VARIABLE = "TORCHCOR_BIN"


def torchcor_environment_diagnostics(
    workflow_dag: Mapping[str, Any], env: Mapping[str, str], driver_context: Any,
) -> tuple[StrictDiagnostic, ...]:
    commands = sorted({step["command"] for step in (workflow_dag or {}).get("steps", ()) if step.get("command")})
    if not commands:
        return ()
    # Quoted: conformance C9 looks for a planned program as a quoted token.
    named = ", ".join(map(repr, commands))
    path, venv_bin = env.get("PATH", ""), env.get(BIN_VARIABLE)
    python = shutil.which("python3", path=path)
    diagnostics = []
    if python is None:
        diagnostics.append(diagnostic(
            "error", "torchcor_python_not_found", f"{named} runs under python3, which is not on PATH={path!r}",
            source="environment",
        ))
    # The shell `omnidriver env` prints puts TORCHCOR_BIN on PATH without
    # exporting it, so only a supplied value can be compared.
    elif venv_bin and Path(python).parent.resolve() != Path(venv_bin).expanduser().resolve():
        diagnostics.append(diagnostic(
            "error", "torchcor_python_not_torchcors",
            f"{named} would run under {python}, not the python3 in {BIN_VARIABLE}={venv_bin}; "
            f"put {BIN_VARIABLE} first on PATH (omnidriver env --plugin torchcor prints the prefix)",
            source="environment",
        ))
    repository = getattr(driver_context, "repository", None)
    supplied = env.get(REPOSITORY_VARIABLE)
    if repository is not None and supplied and Path(supplied).expanduser().resolve() != Path(repository.root).resolve():
        diagnostics.append(diagnostic(
            "error", "torchcor_repository_mismatch",
            f"{REPOSITORY_VARIABLE}={supplied} is not the selected repository {repository.root}; "
            "the keys would be judged by another runner than the one that runs",
            source="environment", field=REPOSITORY_VARIABLE,
        ))
    return tuple(diagnostics)
