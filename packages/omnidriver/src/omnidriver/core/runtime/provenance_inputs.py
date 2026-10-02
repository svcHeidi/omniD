"""Enumerate a case's canonical provenance inputs.

Classification is by consumption, not authorship: e.g. ``constant/polyMesh``
is written by ``blockMesh`` and then read by the solver, so it is generated
and still a mandatory input.
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import shutil
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from ..plugin_interface import ResolvedInput, RuntimeDependency
from .provenance import ProvenanceComponent, component_for_path
from .provenance_dependencies import (
    component_for_runtime_dependency,
    component_for_verified_absence,
)
from . import mpi
from .workflow import case_script_commands
from .workflow_runner import _resolve_case_cwd, _resolve_command

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


def _case_root_dirnames(driver_context: "DriverContext") -> tuple[str, ...]:
    """Top-level case directories the active plugin's declared case files live under, derived from each ``case_files`` rule's first path segment."""
    rules = driver_context.stack.call("get_profile").case_files
    segments = {Path(rule.path).parts[0] for rule in rules if rule.path}
    return tuple(sorted(segments))


def _walk_files(root: Path) -> list[Path]:
    """Every file (or symlink, valid or broken) under ``root``, recursively.

    Plain sub-directories are not emitted -- only leaves. A symlink is always
    emitted regardless of what it resolves to, so a required-but-broken link
    still surfaces (via ``component_for_path``'s own unavailable handling)
    instead of silently vanishing from the walk.
    """
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        found.append(path)
    return sorted(found)


def _matches_any_glob(rel_path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in patterns)


def _collect_consumed_relpaths(workflow_dag: Mapping[str, Any] | None) -> set[str]:
    relpaths: set[str] = set()
    for step in (workflow_dag or {}).get("steps", ()):
        for entry in step.get("consumes", ()) or ():
            relpaths.add(str(entry))
    return relpaths


def _component_for_resolved_input(
    resolved_input: ResolvedInput, case_root: Path
) -> ProvenanceComponent | None:
    """A plugin-resolved required input, fingerprinted -- or, for a
    ``required`` input that failed to resolve, an explicit ``unavailable``
    component. A ``required=False`` input with no resolved path was
    genuinely absent and optional: nothing is fingerprinted."""
    path = resolved_input.path
    if path is None:
        if not resolved_input.required:
            return None
        return ProvenanceComponent(
            kind="case_file",
            path=resolved_input.name,
            role="required_input",
            method="unavailable",
            strength="unavailable",
        )
    try:
        path.relative_to(case_root)
    except ValueError:
        # Resolved outside the case tree entirely (not even via a symlink
        # component_for_path would classify as external_link) -- identify it
        # by the plugin's own declared name, the same pattern
        # provenance_dependencies.py uses for runtime dependencies.
        component = component_for_path(path, kind="case_file", relative_to=path.parent)
        return replace(component, path=resolved_input.name)
    return component_for_path(path, kind="case_file", relative_to=case_root)


def _is_case_local_script(
    command: str,
    executable: str,
    *,
    resolved_cwd: Path,
    case_root: Path,
    driver_context: "DriverContext | None" = None,
) -> Path | None:
    """If ``_resolve_command`` would run a script from inside the case tree
    for this exact ``command``, return its on-disk path; else ``None``.

    Mirrors ``_resolve_command``'s own precondition (an explicit path, or a
    recognized case-script name) rather than re-deciding independently --
    checking existence for every bare command name here would find files the
    real executor's PATH-only bare-name rule would never run.
    """
    if "/" not in command and command not in case_script_commands(driver_context):
        return None
    candidate = Path(executable)
    if not candidate.is_absolute():
        candidate = resolved_cwd / candidate
    if not candidate.is_file():
        return None
    try:
        within_case = candidate.resolve().is_relative_to(case_root.resolve())
    except OSError:
        return None
    return candidate if within_case else None


def _resolve_dependency_path(
    name: str, *, resolved_cwd: Path, env: Mapping[str, str]
) -> Path | None:
    """Where a step executable that is *not* a case-local script lives:
    an explicit path resolved against the step's cwd, or a PATH lookup for a
    bare name -- the same two cases ``_resolve_command`` distinguishes."""
    if "/" in name:
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = resolved_cwd / candidate
        return candidate if candidate.is_file() else None
    # An explicit empty/absent PATH must mean "nothing is found", matching
    # what the real subprocess call would see -- shutil.which's own fallback
    # to the real os.environ on a bare ``None`` would silently defeat a
    # caller's isolated ``env``.
    found = shutil.which(name, path=env.get("PATH", ""))
    return Path(found) if found else None


def _step_command_and_args(step: Mapping[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    raw_command = str(step.get("command", "")).strip()
    if not raw_command:
        return None
    try:
        command, *inline_args = shlex.split(raw_command)
    except ValueError:
        command, *inline_args = raw_command.split()
    if not command:
        return None
    args = tuple(inline_args) + tuple(str(arg) for arg in step.get("args", ()))
    return command, args


def _register_step_executable(
    name: str,
    *,
    resolved_cwd: Path,
    case_root: Path,
    env: Mapping[str, str],
    add_case_file: "_ComponentAdder",
    dependencies: dict[str, RuntimeDependency],
    driver_context: "DriverContext | None" = None,
) -> None:
    executable = _resolve_command(name, resolved_cwd, driver_context)
    local_script = _is_case_local_script(
        name, executable,
        resolved_cwd=resolved_cwd, case_root=case_root, driver_context=driver_context,
    )
    if local_script is not None:
        add_case_file(component_for_path(local_script, kind="case_file", relative_to=case_root))
        return
    dependencies[name] = RuntimeDependency(
        name=name,
        path=_resolve_dependency_path(name, resolved_cwd=resolved_cwd, env=env),
        required=True,
    )


class _ComponentAdder:
    """Callable wrapper so a bound helper can carry a type hint above."""

    def __init__(self, sink: dict[tuple[str, str], ProvenanceComponent]) -> None:
        self._sink = sink

    def __call__(self, component: ProvenanceComponent | None) -> None:
        if component is not None:
            self._sink[(component.kind, component.path)] = component


def _input_roots(stack, case_root: Path, resolved_case, conventions) -> tuple[str, ...]:
    """The stack's input roots, each a non-empty ``str`` inside the case: a
    blank root is the whole case tree, and an absolute or escaping one walks
    outside it."""
    roots = stack.call("get_input_roots", case_root, resolved_case, conventions=conventions)
    for root in roots:
        parts = PurePosixPath(root).parts if isinstance(root, str) else ()
        if not parts or PurePosixPath(root).is_absolute() or ".." in parts:
            raise TypeError(
                f"get_input_roots() must return non-empty case-relative str paths "
                f"inside the case, got {root!r}"
            )
    return roots


def enumerate_case_inputs(
    case_root: Path,
    *,
    workflow_dag: dict[str, Any],
    driver_context: "DriverContext",
    env: Mapping[str, str] | None = None,
) -> tuple[ProvenanceComponent, ...]:
    """Enumerate every provenance input a run of ``workflow_dag`` against
    ``case_root`` consumes: case files, case-local scripts, step executables,
    and plugin-declared runtime dependencies. Excludes generated outputs.

    Resolution precedence, first match wins: a DAG step's ``consumes``
    declaration; a plugin ``required_inputs()`` entry; a plugin
    ``generated_output_globs()`` match (excluded); otherwise required
    input -- an unclassified file must never look like a generated output.

    Never raises on an incomplete or minimal case: every filesystem read
    here degrades to an ``unavailable`` component rather than propagating
    an exception.
    """
    case_root = Path(case_root)
    environment = dict(os.environ) if env is None else dict(env)
    from ..runtime_records import case_runtime_conventions

    stack = driver_context.stack
    resolved_case = stack.call("resolve_case_models", case_root)
    conventions = case_runtime_conventions(driver_context)

    consumed_relpaths = _collect_consumed_relpaths(workflow_dag)
    required_inputs = stack.call("get_required_inputs", case_root, resolved_case)
    generated_globs = stack.call("get_generated_output_globs", case_root, resolved_case)

    components: dict[tuple[str, str], ProvenanceComponent] = {}
    add = _ComponentAdder(components)

    # Every top-level directory the active plugin declares a case file
    # under, plus every input root the plugin declares (for OpenFOAM: the
    # selected start time, serially and in each replica). Plugin
    # required_inputs are applied uniformly below instead, since a
    # resolved input's path need not fall under any of these directories.
    walk_roots = [case_root / d for d in _case_root_dirnames(driver_context)]
    walk_roots.extend(
        case_root / root
        for root in _input_roots(stack, case_root, resolved_case, conventions)
    )

    for root in walk_roots:
        for path in _walk_files(root):
            rel = path.relative_to(case_root).as_posix()
            if rel in consumed_relpaths:
                add(component_for_path(path, kind="case_file", relative_to=case_root))
                continue
            if _matches_any_glob(rel, generated_globs):
                continue
            add(component_for_path(path, kind="case_file", relative_to=case_root))

    # -- Precedence step 2: plugin-resolved required inputs always win,
    # regardless of whether the walk above already included or excluded
    # them (e.g. a field resolved outside the selected time via backward
    # findInstance, or one explicitly re-included over a generated glob).
    for resolved_input in required_inputs:
        add(_component_for_resolved_input(resolved_input, case_root))

    # -- Precedence step 1, applied last so it always wins even for a path
    # the walk above excluded or never visited at all.
    for rel in consumed_relpaths:
        add(component_for_path(case_root / rel, kind="case_file", relative_to=case_root))

    # -- step executables, resolved the same way the executor resolves them
    # (workflow_runner._resolve_command), including an MPI launcher's
    # payload. Case-local scripts land as case_file components above; every
    # other command becomes a RuntimeDependency, deduplicated by name so a
    # binary named by two steps (or already declared by the plugin below)
    # fingerprints once.
    dependencies: dict[str, RuntimeDependency] = {}
    for step in (workflow_dag or {}).get("steps", ()):
        parsed = _step_command_and_args(step)
        if parsed is None:
            continue
        command, args = parsed
        resolved_cwd = _resolve_case_cwd(case_root, str(step.get("cwd", ".")))
        _register_step_executable(
            command,
            resolved_cwd=resolved_cwd,
            case_root=case_root,
            env=environment,
            add_case_file=add,
            dependencies=dependencies,
            driver_context=driver_context,
        )
        if command in mpi.LAUNCHERS:
            payload = mpi.program(args)
            if payload:
                _register_step_executable(
                    payload,
                    resolved_cwd=resolved_cwd,
                    case_root=case_root,
                    env=environment,
                    add_case_file=add,
                    dependencies=dependencies,
                    driver_context=driver_context,
                )

    # -- plugin-declared runtime dependencies: the solver binary,
    # its libraries, and any additional runtime inputs the adapter declares
    # pulls in. Authoritative over the generic PATH-only resolution above --
    # it knows the library search directories and required/optional split a
    # bare PATH lookup cannot.
    for dependency in stack.call("get_extra_provenance_paths", case_root):
        dependencies[dependency.name] = dependency

    # An external #include or #includeEtc file is an input even for an
    # untouched case.  Unsupported directive forms become an unavailable
    # witness so a later checkpoint cannot be silently reused as complete.
    inspection = stack.call(
        "inspect_effective_configuration", case_root=case_root, execution_env=environment,
    )
    root_resolved = case_root.resolve()
    verified_optional_absences: set[str] = set()
    for record in inspection:
        dictionary = str(record.get("dictionary", "<unknown>"))
        evaluator = record.get("evaluator")
        if isinstance(evaluator, Mapping):
            evaluator_name = evaluator.get("name")
            evaluator_path = evaluator.get("path")
            if isinstance(evaluator_name, str) and isinstance(evaluator_path, str):
                name = f"effective_config_evaluator:{evaluator_name}"
                dependencies[name] = RuntimeDependency(
                    name=name, path=Path(evaluator_path), required=True,
                )
        if record.get("status") != "inspected":
            name = f"effective_config:unresolved:{dictionary}"
            dependencies[name] = RuntimeDependency(name=name, path=None, required=True)
        for field, absent in (
            ("inspected_files", False),
            ("absent_optional_files", True),
        ):
            for raw_path in record.get(field, ()):
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                try:
                    path.resolve().relative_to(root_resolved)
                except OSError:
                    # An unreadable path belongs in the dependency set; its
                    # fingerprint will be unavailable rather than omitted.
                    pass
                except ValueError:
                    pass
                else:
                    # Case-local files are already fingerprinted by the main
                    # case walk.  An absent optional is the exception: it
                    # needs its own stable witness so a later local file
                    # appearance cannot look like an unrelated addition.
                    if not absent:
                        continue
                name = f"effective_config:{path.resolve()}"
                dependencies[name] = RuntimeDependency(name=name, path=path, required=True)
                if absent:
                    verified_optional_absences.add(name)

    for dependency in dependencies.values():
        if dependency.name in verified_optional_absences:
            add(component_for_verified_absence(dependency))
        else:
            add(component_for_runtime_dependency(dependency))

    return tuple(sorted(components.values(), key=lambda component: (component.kind, component.path)))
