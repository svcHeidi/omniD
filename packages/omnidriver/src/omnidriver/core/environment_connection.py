"""``omnidriver env``: how to prepare a shell for one plugin's stack, checked.

Each provider's manifest declares its part of the connection
(``plugin_profile.EnvironmentConnection``): the variables an operator
supplies, which one names a file to source, which name directories to put
first on ``PATH``, and its MPI launcher. The stack's connection is every
provider's, least-specific first; the C++ source-root variable a profile's
``cxx_mapping`` names is one more supplied variable.

This module renders and checks. It reads values only from the environment it
is given, sources and exports only what is supplied, and invents no path: an
unset required variable is refused by name, and nothing is searched for.
The check is the stack's own preflight (``EnvironmentPreflightCapability``),
run on the environment the rendered prefix produces, over the stack's solver
commands and, where a launcher is declared, a parallel solve.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Mapping

from .plugin_profile import EnvironmentConnection, SuppliedVariable
from .runtime import mpi

if TYPE_CHECKING:
    from .plugin_interface import DriverContext

#: The launcher's process count in the checked parallel solve: the smallest
#: that is parallel.
_PROBE_RANKS = 2


def stack_connection(driver_context: "DriverContext") -> tuple[EnvironmentConnection, dict[str, str]]:
    """The composed connection, and which provider declared each variable."""
    supplied: dict[str, SuppliedVariable] = {}
    declared_by: dict[str, str] = {}
    source: str | None = None
    path_prepend: list[str] = []
    launcher: str | None = None
    for provider in driver_context.providers:
        profile = provider.get_profile()
        connection = profile.environment or EnvironmentConnection()
        for variable in connection.supplied:
            supplied[variable.name] = variable
            declared_by[variable.name] = profile.plugin_id
        if connection.source is not None:
            if source is not None and source != connection.source:
                raise ValueError(
                    f"two providers name a file to source ({source}, {connection.source}); "
                    "a stack has one environment to source"
                )
            source = connection.source
        path_prepend += [name for name in connection.path_prepend if name not in path_prepend]
        launcher = connection.mpi_launcher or launcher
        mapping = profile.cxx_mapping
        if mapping is not None and mapping.source_root_variable not in supplied:
            supplied[mapping.source_root_variable] = SuppliedVariable(
                mapping.source_root_variable, False,
                f"the native tree; its {mapping.source_root_relative} is the C++ source the "
                "key scanner reads in every strict plan (cxx_mapping.source_root)",
            )
            declared_by[mapping.source_root_variable] = profile.plugin_id
    return EnvironmentConnection(
        supplied=tuple(supplied.values()), source=source,
        path_prepend=tuple(path_prepend), mpi_launcher=launcher,
    ), declared_by


def render_prefix(connection: EnvironmentConnection, environ: Mapping[str, str]) -> str:
    """The bash commands that prepare the shell, in the one safe order:
    source first, then every other supplied variable exported with its
    literal value (macOS strips ``DYLD_*`` when bash starts), then ``PATH``."""
    parts = []
    if connection.source is not None and environ.get(connection.source):
        parts.append(f"source {shlex.quote(environ[connection.source])}")
    skip = {connection.source, *connection.path_prepend}
    exports = [
        f"{variable.name}={shlex.quote(environ[variable.name])}"
        for variable in connection.supplied
        if variable.name not in skip and environ.get(variable.name)
    ]
    if exports:
        parts.append("export " + " ".join(exports))
    prepend = [shlex.quote(environ[name]) for name in connection.path_prepend if environ.get(name)]
    if prepend:
        parts.append(f'export PATH={":".join(prepend)}:"$PATH"')
    return "".join(f"{part}; " for part in parts)


#: Prints the environment it was started with. Run by this Python, not by
#: ``env``: macOS strips ``DYLD_*`` again when bash starts a system binary.
_DUMP = "import json, os, sys; sys.stdout.write(json.dumps(dict(os.environ)))"


def _apply(prefix: str, environ: Mapping[str, str]) -> tuple[dict[str, str] | None, str | None]:
    """The environment ``prefix`` leaves in a fresh bash, or the error."""
    try:
        completed = subprocess.run(
            ("bash", "-c", f"set +eu; {prefix}exec {shlex.quote(sys.executable)} -c {shlex.quote(_DUMP)}"),
            env=dict(environ), capture_output=True, text=True, timeout=60, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if completed.returncode != 0:
        return None, completed.stderr.strip()[-600:] or f"exit {completed.returncode}"
    return json.loads(completed.stdout), None


def _diagnostic(level: str, code: str, message: str, field: str = "") -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "source": "environment", "field": field}


def environment_report(driver_context: "DriverContext", environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    environ = dict(os.environ if environ is None else environ)
    connection, declared_by = stack_connection(driver_context)
    variables = [
        {
            "name": variable.name, "required": variable.required, "set": bool(environ.get(variable.name)),
            "value": environ.get(variable.name), "why": variable.why, "declared_by": declared_by[variable.name],
        }
        for variable in connection.supplied
    ]
    diagnostics = [
        _diagnostic("error", "environment_variable_not_supplied",
                    f"{item['name']} is not set: {item['why']}", item["name"])
        for item in variables if item["required"] and not item["set"]
    ]
    for provider in driver_context.providers:
        mapping = provider.get_profile().cxx_mapping
        root = mapping.source_root(environ) if mapping is not None else None
        if root is not None and not root.is_dir():
            diagnostics.append(_diagnostic(
                "error", "plugin_cxx_source_unavailable",
                f"{mapping.source_root_variable} is supplied, but its C++ source {root} is not a "
                "directory; every strict plan would refuse it", mapping.source_root_variable,
            ))
    report: dict[str, Any] = {
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "variables": variables,
        "shell_prefix": None,
        "launcher": None,
        "commands": {},
        "preflight": diagnostics,
    }
    if diagnostics:
        report["status"] = "failed"
        return report
    prefix = render_prefix(connection, environ)
    report["shell_prefix"] = prefix
    applied, error = _apply(prefix, environ)
    if applied is None:
        diagnostics.append(_diagnostic("error", "environment_prefix_failed", f"bash -c {prefix!r}: {error}"))
        report["status"] = "failed"
        return report

    authorization = driver_context.capabilities.command_authorization
    solvers = sorted(authorization.solver_commands())
    others = sorted((authorization.auxiliary_commands() | authorization.environment_commands()) - set(solvers))
    report["commands"] = {
        command: shutil.which(command, path=applied.get("PATH"))
        for command in (*solvers, *others)
    }
    steps = [{"id": command, "command": command, "args": []} for command in solvers]
    if connection.mpi_launcher is not None:
        report["launcher"] = mpi.identity(connection.mpi_launcher, applied)
        steps += [
            mpi.wrap({"id": f"{command}.parallel", "command": command}, _PROBE_RANKS, connection.mpi_launcher)
            for command in solvers
        ]
    preflight = driver_context.capabilities.environment_preflight.diagnostics(
        {"steps": steps}, env=applied, driver_context=driver_context,
    )
    diagnostics += [asdict(item) if not isinstance(item, dict) else dict(item) for item in preflight]
    report["status"] = "failed" if any(item["level"] == "error" for item in diagnostics) else "ok"
    return report
