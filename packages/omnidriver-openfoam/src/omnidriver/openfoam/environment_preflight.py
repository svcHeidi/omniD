from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.runtime.workflow import (
    _MPI_LAUNCHERS,
    _unwrap_mpi_program,
    case_script_commands,
)
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
        if command in _MPI_LAUNCHERS:
            is_parallel = True
            mpi_launcher_in_dag = True
            _add(command)
            wrapped = _unwrap_mpi_program(args)
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


_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})


def _supplied_src_root(driver_context: Any | None) -> Path | None:
    """The stack's C++ source root, as supplied (``cxx_mapping.source_root``),
    or ``None`` -- never discovered by walking up from this module."""
    if driver_context is None:
        return None
    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    return mapping.source_root(os.environ) if mapping is not None else None


def _newest_source_mtime(src_root: Path) -> float | None:
    """Return the mtime of the most recently modified C++/CUDA source under
    ``src_root``, or ``None`` if there are no source files."""
    newest: float | None = None
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for name in filenames:
            if os.path.splitext(name)[1] in _SOURCE_SUFFIXES:
                mtime = os.path.getmtime(os.path.join(dirpath, name))
                if newest is None or mtime > newest:
                    newest = mtime
    return newest


def _build_staleness_diagnostics(
    workflow_dag: dict[str, Any] | None,
    checked_env: dict[str, str],
    *,
    src_root: Path | str | None,
    driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """Warn (never block) when a user-compiled utility under
    ``$FOAM_USER_APPBIN`` is older than the newest source under ``src_root``
    -- the classic stale-``libso`` footgun; core OpenFOAM apps are never
    flagged."""
    if src_root is None:
        return ()
    src_root = Path(src_root)
    if not src_root.exists():
        return ()

    user_appbin = checked_env.get("FOAM_USER_APPBIN")
    if not user_appbin:
        return ()
    user_appbin_resolved = Path(user_appbin).resolve()

    # Find plan binaries that actually live under the user appbin before doing
    # the (potentially large) source-tree walk.
    candidates: list[tuple[str, str]] = []
    path = checked_env.get("PATH")
    for executable in _required_executables(workflow_dag, driver_context).executables:
        resolved = shutil.which(executable, path=path)
        if not resolved:
            continue
        try:
            Path(resolved).resolve().relative_to(user_appbin_resolved)
        except ValueError:
            continue
        candidates.append((executable, resolved))

    if not candidates:
        return ()

    newest_source = _newest_source_mtime(src_root)
    if newest_source is None:
        return ()

    diagnostics: list[StrictDiagnostic] = []
    for executable, resolved in candidates:
        if os.path.getmtime(resolved) < newest_source:
            diagnostics.append(diagnostic(
                "warning",
                "stale_build",
                f"{executable} is older than the newest source under {src_root}; "
                "rebuild (e.g. wmake / wmake libso) before running.",
                source="environment",
                field=executable,
            ))
    return tuple(diagnostics)


#: ``WM_MPLIB`` (set by OpenFOAM's bashrc) -> words ``mpirun --version``
#: prints for that MPI family. Open MPI prints ``mpirun (Open MPI) 5.0.9``;
#: MPICH's hydra prints ``HYDRA build details``.
_MPI_FAMILY_MARKERS = {
    "OPENMPI": ("Open MPI", "OpenRTE"),
    "MPICH": ("HYDRA", "MPICH"),
    "INTELMPI": ("Intel",),
}


def _mpi_family_diagnostics(checked_env: dict[str, str]) -> tuple[StrictDiagnostic, ...]:
    """The ``mpirun`` on PATH must match ``WM_MPLIB``, the MPI family
    OpenFOAM was sourced with -- another MPI's launcher first on PATH
    (openCARP's bundled MPICH, say) starts N separate serial solvers instead
    of one N-rank run. An unknown family is not checked."""
    mplib = checked_env.get("WM_MPLIB", "")
    markers = next((words for family, words in _MPI_FAMILY_MARKERS.items() if family in mplib), None)
    launcher = shutil.which("mpirun", path=checked_env.get("PATH"))
    if markers is None or launcher is None:
        return ()
    try:
        completed = subprocess.run(
            (launcher, "--version"), capture_output=True, text=True,
            env=checked_env, timeout=30, check=False,
        )
        version = (completed.stdout + completed.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        version = str(exc)
    if any(word in version for word in markers):
        return ()
    first_line = version.splitlines()[0] if version else "no output"
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
    if "SKIP_ENV_DIAGNOSTICS" in os.environ:
        return ()
    diagnostics: list[StrictDiagnostic] = []
    checked_env = env
    loaded_environment = None
    if checked_env is None:
        loaded_environment = load_openfoam_environment(
            bashrc_path=bashrc_path,
            driver_context=driver_context,
        )
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
                "WM_PROJECT_DIR is not set. OpenFOAM environment not sourced.",
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

    diagnostics.extend(
        _build_staleness_diagnostics(
            workflow_dag, checked_env, src_root=_supplied_src_root(driver_context),
            driver_context=driver_context,
        )
    )

    return tuple(diagnostics)
