"""The programs a plan runs, and the one preflight that each is on PATH."""
from __future__ import annotations

import shlex
import shutil
from typing import Any, Mapping

from ..planning_types import StrictDiagnostic, diagnostic
from ..scripts import find_script
from . import mpi
from .workflow import case_script_commands

#: The code of a planned program the checked PATH does not resolve; ``field`` names the program.
PROGRAM_NOT_ON_PATH = "program_not_on_path"


def planned_programs(workflow_dag: Mapping[str, Any] | None, driver_context: Any | None = None) -> tuple[str, ...]:
    """Each program the plan's steps start from PATH, in step order: a launcher and the program it runs.

    A case script is not looked up on PATH, so it is not listed; a repository
    ``.py`` script runs under the ``python3`` on PATH, which is listed in its place."""
    case_scripts = case_script_commands(driver_context)
    programs: list[str] = []

    def _add(name: str | None) -> None:
        if not name or name.removeprefix("./") in case_scripts:
            return
        script = find_script(name, driver_context)
        if script is not None:
            name = "python3" if script.suffix == ".py" else None
        if name and name not in programs:
            programs.append(name)

    for step in (workflow_dag or {}).get("steps", ()):
        raw = str(step.get("command") or "").strip()
        if not raw:
            continue
        # A step's command may carry its whole invocation ("postProcess -func probes").
        try:
            command, *inline = shlex.split(raw)
        except ValueError:
            command, *inline = raw.split()
        _add(command)
        if command in mpi.LAUNCHERS:
            _add(mpi.program([*inline, *(str(arg) for arg in step.get("args", ()))]))
    return tuple(programs)


def program_diagnostics(
    workflow_dag: Mapping[str, Any] | None, env: Mapping[str, str], driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """An error for each planned program ``env``'s PATH does not resolve."""
    path = env.get("PATH", "")
    return tuple(
        diagnostic("error", PROGRAM_NOT_ON_PATH, f"{program!r} is not on PATH={path!r}",
                   source="environment", field=program)
        for program in planned_programs(workflow_dag, driver_context)
        if shutil.which(program, path=path) is None
    )
