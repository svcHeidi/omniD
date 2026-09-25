"""Preflight and log redaction (evidence A4-A8, G3).

openCARP's whole environment is its binaries plus one library path, supplied
ambiently (A6): nothing here sources a shell profile or searches for one."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Mapping

from omnidriver.core.planning_types import StrictDiagnostic

from .catalog import load_catalog

SOLVER_COMMANDS = frozenset({"openCARP"})
AUXILIARY_COMMANDS = frozenset({"mesher", "igbextract", "igbhead"})
# G3: every openCARP run prints its build header, whose repository line
# embeds a CI token. The whole credential part of any such URL is replaced.
# Core's workflow_runner.redact_step_logs replaces every match whole, so the
# pattern matches only the credential (review I3, 2026-09-25: it was
# ``(https?://)[^/\s@]+(?=@)``, relying on a keep-group-1 rule core no
# longer has). Corrected 2026-09-25: this said the pattern was not yet called
# by anything; Task 12 consumes it, and test_conformance_native.py's
# test_no_token_survives_in_workflow_logs exercises it on the real binary.
REDACTION_PATTERNS = (r"(?<=://)[^/\s@]+(?=@)",)
# ``-buildinfo``'s tag line, e.g. ``*** GIT tag:            v18.1`` (v18.1).
_GIT_TAG = re.compile(r"GIT tag:\s*(\S+)")


def opencarp_environment_diagnostics(workflow_dag: Mapping[str, Any], env: Mapping[str, str]) -> tuple[StrictDiagnostic, ...]:
    path = env.get("PATH", "")
    commands = sorted({step.get("command") for step in (workflow_dag or {}).get("steps", ()) if step.get("command")})
    # The command is quoted (``!r``): conformance C9 looks for the solver as a
    # quoted token once the PATH echoed here is removed (final review S-I2),
    # so an unquoted name, or the name inside a scratch path, never counts.
    diagnostics = [
        StrictDiagnostic(level="error", code="opencarp_command_not_found",
                         message=f"{command!r} is not on PATH={path!r}")
        for command in commands if shutil.which(command, path=path) is None
    ]
    solver = shutil.which("openCARP", path=path)
    if solver is not None and "openCARP" in commands:
        proc = subprocess.run([solver, "-buildinfo"], capture_output=True, text=True, env=dict(env), timeout=60)
        if "GIT tag" not in proc.stdout:
            diagnostics.append(StrictDiagnostic(
                level="error", code="opencarp_binary_unloadable",
                message="'openCARP' is on PATH but cannot start; on macOS set DYLD_LIBRARY_PATH to the "
                        "directory holding libsundials_cvode (A4-A6): " + proc.stderr.strip()[-300:],
            ))
        else:
            diagnostics.extend(_version_diagnostics(proc.stdout))
    return tuple(diagnostics)


def _version_diagnostics(buildinfo: str) -> tuple[StrictDiagnostic, ...]:
    """A warning, not an error, when the binary's ``GIT tag`` differs from
    the tag the committed parameter catalogue was generated from (final
    review S-M3, 2026-09-25): the validator certifies keys, menus and bounds
    against that catalogue, so a different build may accept or mean
    something else. Only the tags are quoted; ``-buildinfo``'s other lines
    are never echoed (G3)."""
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
