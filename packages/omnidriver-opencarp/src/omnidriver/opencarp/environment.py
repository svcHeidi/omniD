"""Preflight and log redaction.

openCARP's whole environment is its binaries plus one library path, supplied ambiently: nothing here sources a shell profile or searches for one."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.planning_types import StrictDiagnostic
from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import file_digest
from omnidriver.core.runtime.planned_programs import planned_programs, program_diagnostics

from .catalog import load_catalog

SOLVER_COMMANDS = frozenset({"openCARP"})
AUXILIARY_COMMANDS = frozenset({"mesher", "igbextract", "igbhead"})
# Every openCARP run prints its build header, whose repository line embeds
# a CI token. Core's workflow_runner.redact_step_logs replaces every match
# whole, so the pattern matches only the credential part of that URL.
REDACTION_PATTERNS = (r"(?<=://)[^/\s@]+(?=@)",)
# ``-buildinfo``'s tag line, e.g. ``*** GIT tag:            v18.1`` (v18.1).
_GIT_TAG = re.compile(r"GIT tag:\s*(\S+)")
_GIT_HASH = re.compile(r"GIT hash:\s*(\S+)")


def buildinfo_identity(buildinfo: str) -> dict[str, str | None] | None:
    """``-buildinfo``'s tag and hash, or ``None`` when it prints neither; no other line is read."""
    tag, commit = _GIT_TAG.search(buildinfo), _GIT_HASH.search(buildinfo)
    if tag is None and commit is None:
        return None
    return {"tag": tag.group(1) if tag else None, "commit": commit.group(1) if commit else None}


def opencarp_solver_builds(
    env: Mapping[str, str], *, used_paths: frozenset | None, solver: str,
) -> tuple[SolverEntry, ...]:
    """openCARP as its own ``-buildinfo`` reports it, when a plan runs it, under the label ``solver``."""
    binary = shutil.which("openCARP", path=env.get("PATH", ""))
    if binary is None or (used_paths is not None and Path(binary).resolve() not in used_paths):
        return ()
    try:
        identity = buildinfo_identity(subprocess.run(
            [binary, "-buildinfo"], capture_output=True, text=True, env=dict(env), timeout=60,
        ).stdout)
    except (OSError, subprocess.TimeoutExpired):
        identity = None
    build = SolverBuild(
        name="openCARP", path=Path(binary), digest=file_digest(Path(binary)),
        known="self_reported" if identity else "unknown",
        source=SourceIdentity(git=identity) if identity else None,
    )
    return (SolverEntry(solver=solver, repository=None, builds=(build,)),)


def opencarp_environment_diagnostics(
    workflow_dag: Mapping[str, Any], env: Mapping[str, str], driver_context: Any | None = None,
) -> tuple[StrictDiagnostic, ...]:
    from .parallel import SOLVER, launcher_diagnostics

    diagnostics = list(program_diagnostics(workflow_dag, env, driver_context))
    solver = shutil.which(SOLVER, path=env.get("PATH", ""))
    if solver is not None and SOLVER in planned_programs(workflow_dag, driver_context):
        proc = subprocess.run([solver, "-buildinfo"], capture_output=True, text=True, env=dict(env), timeout=60)
        if "GIT tag" not in proc.stdout:
            diagnostics.append(StrictDiagnostic(
                level="error", code="opencarp_binary_unloadable",
                message="'openCARP' is on PATH but cannot start; on macOS set DYLD_LIBRARY_PATH to the "
                        "directory holding libsundials_cvode (A4-A6): " + proc.stderr.strip()[-300:],
            ))
        else:
            diagnostics.extend(_version_diagnostics(proc.stdout))
            diagnostics.extend(launcher_diagnostics(workflow_dag, env))
    return tuple(diagnostics)


def _version_diagnostics(buildinfo: str) -> tuple[StrictDiagnostic, ...]:
    """A warning, not an error, when the binary's ``GIT tag`` differs from the tag the committed parameter catalogue was generated from: the validator certifies keys, menus and bounds against that catalogue, so a different build may accept or mean something else. Only the tags are quoted; ``-buildinfo``'s other lines are never echoed."""
    match = _GIT_TAG.search(buildinfo)
    expected = load_catalog().identity.get("tag")
    found = match.group(1) if match else None
    if found == expected:
        return ()
    return (StrictDiagnostic(
        level="warning", code="opencarp_version_mismatch",
        message=f"openCARP on PATH reports GIT tag {found!r}, but the committed parameter catalogue "
                f"was generated from {expected!r}; keys, menus and bounds are validated against "
                f"{expected!r}, so regenerate the catalogue (scripts/generate-opencarp-catalog.py) "
                "for this build",
    ),)
