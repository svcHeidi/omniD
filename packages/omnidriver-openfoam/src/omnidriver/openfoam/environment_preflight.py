from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.runtime import mpi
from omnidriver.core.runtime.planned_programs import planned_programs, program_diagnostics
from .openfoam_environment import load_openfoam_environment


#: Programs a plan may run that OpenFOAM's environment does not supply.
_INTERPRETERS = frozenset({"python", "python3"})


@dataclass(frozen=True)
class _ExecutableRequirements:
    executables: tuple[str, ...]
    is_parallel: bool
    mpi_launcher_in_dag: bool


def _required_executables(
    workflow_dag: dict[str, Any] | None, driver_context: Any | None = None,
) -> _ExecutableRequirements:
    """The plan's programs, and whether it runs in parallel and names its launcher."""
    is_parallel = False
    mpi_launcher_in_dag = False
    for step in (workflow_dag or {}).get("steps", ()):
        command, *args = str(step.get("command", "")).split() or [""]
        args += [str(arg) for arg in step.get("args", ())]
        if command in mpi.LAUNCHERS:
            is_parallel = mpi_launcher_in_dag = True
        elif command == "decomposePar" or "-parallel" in args:
            is_parallel = True
    return _ExecutableRequirements(
        executables=planned_programs(workflow_dag, driver_context),
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
    plan_needs_openfoam = (
        any(program not in _INTERPRETERS for program in requirements.executables) or requirements.is_parallel
    )

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

    diagnostics.extend(program_diagnostics(workflow_dag, checked_env, driver_context))

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
