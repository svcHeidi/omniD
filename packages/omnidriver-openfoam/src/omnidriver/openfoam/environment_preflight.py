from __future__ import annotations

import os
import re
import shlex
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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


_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})


def _supplied_src_root(driver_context: Any | None) -> Path | None:
    """The stack's supplied C++ source root (``cxx_mapping.source_root``), or ``None``; never discovered."""
    if driver_context is None:
        return None
    mapping = driver_context.stack.call("get_profile").cxx_mapping
    return mapping.source_root(os.environ) if mapping is not None else None


#: A wmake library rule: the library a ``Make/files`` builds from the sources
#: beside its ``Make`` directory.
_LIB_RULE = re.compile(r"^\s*LIB\s*=\s*\$\(FOAM_USER_LIBBIN\)/(\S+)", re.MULTILINE)


def _sources(directory: Path) -> list[tuple[float, Path]]:
    """Every C++/CUDA source under ``directory`` with its mtime; wmake's ``Make`` and ``lnInclude`` are not source."""
    found: list[tuple[float, Path]] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [name for name in dirnames if name not in {"Make", "lnInclude"}]
        for name in filenames:
            if os.path.splitext(name)[1] in _SOURCE_SUFFIXES:
                path = Path(dirpath, name)
                found.append((os.path.getmtime(path), path))
    return found


def _stale_build(name: str, built: Path, sources: list[tuple[float, Path]], root: Path) -> StrictDiagnostic | None:
    """A warning naming ``built`` when sources under ``root`` are newer than it."""
    newer = [(mtime, path) for mtime, path in sources if mtime > os.path.getmtime(built)]
    if not newer:
        return None
    newest_mtime, newest = max(newer)

    def when(stamp: float) -> str:
        return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M:%S")

    return diagnostic(
        "warning",
        "stale_build",
        f"{name} ({built}, built {when(os.path.getmtime(built))}) is older than {len(newer)} source "
        f"file(s) under {root}, the newest {newest.relative_to(root)} ({when(newest_mtime)}): the plan and "
        "the scan read that source, so they describe a state this binary was not built from; "
        "rebuild (e.g. wmake / wmake libso) before running.",
        source="environment",
        field=name,
    )


def _build_staleness_diagnostics(
    workflow_dag: dict[str, Any] | None,
    checked_env: dict[str, str],
    *,
    src_root: Path | str | None,
    driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """Warn, never block, when a user-compiled utility or library built from ``src_root`` is older than its sources."""
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

    sources = _sources(src_root)
    built = [(executable, Path(resolved), sources) for executable, resolved in candidates]
    libbin = checked_env.get("FOAM_USER_LIBBIN")
    if libbin:
        for make_files in sorted(src_root.rglob("Make/files")):
            for lib in _LIB_RULE.findall(make_files.read_text(errors="replace")):
                path = next((p for p in Path(libbin).glob(f"{lib}.*") if p.suffix in {".so", ".dylib"}), None)
                if path is not None:
                    built.append((lib, path, _sources(make_files.parent.parent)))
    return tuple(
        found for name, path, own in built
        if (found := _stale_build(name, path, own, src_root)) is not None
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

    diagnostics.extend(
        _build_staleness_diagnostics(
            workflow_dag, checked_env, src_root=_supplied_src_root(driver_context),
            driver_context=driver_context,
        )
    )

    return tuple(diagnostics)
