from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.runtime import mpi
from omnidriver.core.runtime.workflow import case_script_commands
from omnidriver.core.scripts import find_script
from .openfoam_environment import load_openfoam_environment


_INTERPRETER_SKIP = frozenset({"python", "python3"})


@dataclass(frozen=True)
class _ExecutableRequirements:
    executables: tuple[str, ...]
    is_parallel: bool
    mpi_launcher_in_dag: bool


def _required_executables(
    workflow_dag: dict[str, Any] | None, driver_context: Any | None = None,
) -> _ExecutableRequirements:
    """Derive the executables a plan will invoke from its workflow DAG."""
    executables: list[str] = []
    is_parallel = False
    mpi_launcher_in_dag = False
    case_scripts = case_script_commands(driver_context)

    def _add(name: str) -> None:
        if (
            name
            and name not in _INTERPRETER_SKIP
            and name not in case_scripts
            and find_script(name, driver_context) is None
            and name not in executables
        ):
            executables.append(name)

    for step in (workflow_dag or {}).get("steps", ()):
        raw_command = str(step.get("command", "")).strip()
        args = tuple(str(arg) for arg in step.get("args", ()))
        if not raw_command:
            continue
        # "command" may carry the whole invocation (e.g. "postProcess -func
        # Niedererpoints -latestTime"); only the leading token is the executable.
        try:
            command, *inline_args = shlex.split(raw_command)
        except ValueError:
            command, *inline_args = raw_command.split()
        if not command:
            continue
        args = tuple(inline_args) + args
        if command in mpi.LAUNCHERS:
            is_parallel = True
            mpi_launcher_in_dag = True
            _add(command)
            wrapped = mpi.program(args)
            if wrapped is not None:
                _add(wrapped)
            continue
        if command == "decomposePar" or "-parallel" in args:
            is_parallel = True
        _add(command)

    return _ExecutableRequirements(
        executables=tuple(executables),
        is_parallel=is_parallel,
        mpi_launcher_in_dag=mpi_launcher_in_dag,
    )


#: ``WM_MPLIB`` (set by OpenFOAM's bashrc) -> words ``mpirun --version``
#: prints for that MPI family. Open MPI prints ``mpirun (Open MPI) 5.0.9``;
#: MPICH's hydra prints ``HYDRA build details``.
_MPI_FAMILY_MARKERS = {
    "OPENMPI": ("Open MPI", "OpenRTE"),
    "MPICH": ("HYDRA", "MPICH"),
    "INTELMPI": ("Intel",),
}


def _mpi_family_diagnostics(checked_env: dict[str, str]) -> tuple[StrictDiagnostic, ...]:
    """The ``mpirun`` on PATH must match ``WM_MPLIB``, or another MPI's launcher starts N serial solvers; an unknown family is skipped."""
    mplib = checked_env.get("WM_MPLIB", "")
    markers = next((words for family, words in _MPI_FAMILY_MARKERS.items() if family in mplib), None)
    found = mpi.identity("mpirun", checked_env)
    if markers is None or found["path"] is None:
        return ()
    launcher, version = found["path"], " ".join(found["version"] or ())
    if any(word in version for word in markers):
        return ()
    first_line = found["version"][0] if found["version"] else "no output"
    return (diagnostic(
        "error",
        "openfoam_mpi_launcher_mismatch",
        f"mpirun on PATH ({launcher}, {first_line!r}) is not the {mplib} MPI OpenFOAM was "
        "sourced with; a parallel run would start one serial solver per rank. Put "
        "OpenFOAM's MPI first on PATH (source its bashrc last, and never add another "
        "solver's MPI bin to this shell)",
        source="environment",
        field="mpirun",
    ),)


def _environment_diagnostics(
    workflow_dag: dict[str, Any] | None,
    *,
    env: dict[str, str] | None = None,
    bashrc_path: str | None = None,
    driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """Preflight the runtime environment against the plan's actual commands."""
    diagnostics: list[StrictDiagnostic] = []
    checked_env = env
    loaded_environment = None
    if checked_env is None:
        loaded_environment = load_openfoam_environment(bashrc_path=bashrc_path)
        checked_env = loaded_environment.env

    if loaded_environment is not None and loaded_environment.error:
        diagnostics.append(diagnostic(
            "error",
            "openfoam_env_source_failed",
            loaded_environment.error,
            source="environment",
            field=loaded_environment.bashrc or bashrc_path or "",
        ))

    # Derived before the environment checks: whether an unsourced environment
    # is a problem depends on what this plan actually invokes.
    requirements = _required_executables(workflow_dag, driver_context)
    plan_needs_openfoam = bool(requirements.executables) or requirements.is_parallel

    if "WM_PROJECT_DIR" not in checked_env:
        if plan_needs_openfoam:
            diagnostics.append(diagnostic(
                "error",
                "missing_openfoam_env",
                "WM_PROJECT_DIR is not set and no OpenFOAM bashrc was supplied: pass "
                "--environment-source, set OPENFOAM_BASHRC, or name openfoam.bashrc in "
                "the file OMNIDRIVER_RUNTIME_CONFIG points to. OpenFOAM environment not sourced.",
                source="environment",
            ))
        else:
            # Not blocking is not the same as saying nothing: a case script
            # this preflight cannot read into may still want an environment.
            diagnostics.append(diagnostic(
                "warning",
                "openfoam_env_not_sourced",
                "WM_PROJECT_DIR is not set, so the OpenFOAM environment was not "
                "sourced. This plan declares no OpenFOAM executable, so launch is "
                "not blocked; a case script this preflight cannot read may still "
                "expect one.",
                source="environment",
            ))
    else:
        for var in ("WM_PROJECT_VERSION", "FOAM_USER_LIBBIN"):
            if var not in checked_env:
                diagnostics.append(diagnostic(
                    "warning",
                    "partial_openfoam_env",
                    f"{var} is not set. OpenFOAM environment may be partially sourced.",
                    source="environment",
                    field=var,
                ))

    for executable in requirements.executables:
        if not shutil.which(executable, path=checked_env.get("PATH")):
            diagnostics.append(diagnostic(
                "error",
                "missing_executable",
                f"{executable!r} not found on PATH.",
                source="environment",
                field=executable,
            ))

    if (
        requirements.is_parallel
        and not requirements.mpi_launcher_in_dag
        and not (
            shutil.which("mpirun", path=checked_env.get("PATH"))
            or shutil.which("mpiexec", path=checked_env.get("PATH"))
        )
    ):
        diagnostics.append(diagnostic(
            "error",
            "missing_mpi",
            "Plan is parallel but no MPI launcher (mpirun/mpiexec) found on PATH.",
            source="environment",
            field="mpirun",
        ))

    if requirements.mpi_launcher_in_dag:
        diagnostics.extend(_mpi_family_diagnostics(checked_env))

    return tuple(diagnostics)
