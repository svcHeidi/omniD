"""Solver-neutral generic case spec implementation.

Owns the default case-folder execution contract: environment adapters
declare the case entrypoint and output convention, and a generic case folder
declares no catalog, so core (not a solver adapter) owns this module.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from omnidriver.core.specs.paths import (
    resolve_run_script_path,
    resolve_spec_paths,
)

from .models import TutorialSpec
from omnidriver.core.plugin_profile import entrypoint_command

# ``run_case.sh`` ships inside the installed package (``omnidriver/scripts/``),
# not at any path relative to a repo checkout, so it is resolved relative to
# this file. The result is already absolute, so ``resolve_run_script_path``
# returns it unchanged instead of hunting for it under a repo root.
RUN_CASE_SCRIPT_RELPATH = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "run_case.sh"
)


DictFileOverrides = Mapping[str, "Mapping[str, Any] | Sequence[Mapping[str, Any]]"]


def _apply_case(
    case_root: Path,
    *,
    dict_file_relpaths: Mapping[str, Path],
    dict_file_overrides: Mapping[str, Any],
    mutation_callback,
) -> Any:
    return mutation_callback(
        case_root,
        dict_file_relpaths=dict(dict_file_relpaths),
        dict_file_overrides=dict(dict_file_overrides),
    )


def _split_command(command: str | Sequence[str]) -> list[str]:
    return command.split() if isinstance(command, str) else list(command)


def _workflow_dag_for(
    *,
    solver_command: str | Sequence[str] | None,
    pre_solve_commands: Sequence[str | Sequence[str]],
    driver_context: Any | None = None,
) -> dict[str, Any]:
    """Build the workflow DAG for a generic case: with no ``solver_command``
    the whole run is one step invoking the plugin's declared environment
    entrypoint; otherwise the pre-solve commands chained into a solve step."""
    if solver_command is None:
        entrypoint = entrypoint_command(driver_context)
        return {"steps": [{"id": "run", "command": entrypoint, "depends_on": []}]}

    steps: list[dict[str, Any]] = []
    depends_on: list[str] = []
    for index, raw_cmd in enumerate(pre_solve_commands):
        cmd = _split_command(raw_cmd)
        step_id = f"pre_{index}"
        steps.append(
            {
                "id": step_id,
                "command": cmd[0],
                "args": cmd[1:],
                "depends_on": depends_on,
            }
        )
        depends_on = [step_id]

    solve_cmd = _split_command(solver_command)
    steps.append(
        {
            "id": "solve",
            "command": solve_cmd[0],
            "args": solve_cmd[1:],
            "depends_on": depends_on,
        }
    )
    return {"steps": steps}


def _no_solver_mutation(*_args, **_kwargs) -> None:
    """What a case mutation is when no plugin supplies one: nothing."""
    return None


def make_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str,
    setup_dir_name: str | None = None,
    output_dir_name: str | None = None,
    dict_file_relpaths: Mapping[str, str | Path] | None = None,
    dict_file_overrides: DictFileOverrides | None = None,
    dimension: str | None = None,
    parallel: bool = False,
    touch_case_foam: bool = False,
    collect_patterns: Sequence[str] = (),
    run_script_relpath: str | Path = RUN_CASE_SCRIPT_RELPATH,
    driver_context: Any | None = None,
    solver_command: str | Sequence[str] | None = None,
    pre_solve_commands: Sequence[str | Sequence[str]] | None = None,
    _apply_case_mutation=None,
) -> TutorialSpec:
    if not str(case_dir_name).strip():
        raise ValueError("case_dir_name cannot be empty")

    # Configuration files are supplied by the selected adapter. Core does not
    # invent dictionary names for a generic case.
    resolved_relpaths_raw: dict[str, Any] = dict(dict_file_relpaths or {})
    resolved_relpaths = {
        str(key): Path(value) for key, value in resolved_relpaths_raw.items()
    }

    resolved_overrides: dict[str, Any] = dict(dict_file_overrides or {})
    resolved_overrides = {key: value for key, value in resolved_overrides.items() if value}

    run_script_path = Path(run_script_relpath)
    normalized_pre_solve = tuple(pre_solve_commands or ())
    if _apply_case_mutation is None:
        # The adapter that owns configuration mutation supplies its own
        # callback and transaction targets.
        _apply_case_mutation = _no_solver_mutation

    workflow_dag = _workflow_dag_for(
        solver_command=solver_command,
        pre_solve_commands=normalized_pre_solve,
        driver_context=driver_context,
    )

    output_convention = (
        driver_context.capabilities.case_runtime_conventions.conventions()
        .output_collection_relpath
        if driver_context is not None
        else None
    )
    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=output_convention,
    )

    # A generic case folder declares no catalog, so this factory can never
    # produce a ParameterAssignment with a real qualified id, nor
    # RenderedFile bytes of its own -- inventing either would be a
    # discovered-versus-supplied violation. The one honest claim it can make
    # is "nothing was written", true only when no adapter supplied its own
    # callback above (``mutation_callback`` still the ``_no_solver_mutation``
    # sentinel). ``case_mutation`` is called once, either way, and its return
    # (``CaseWriteRecord`` or ``None``) is exactly what the callback itself
    # reports.
    dispatch_case_mutation = partial(
        _apply_case,
        dict_file_relpaths=resolved_relpaths,
        dict_file_overrides=resolved_overrides,
        mutation_callback=_apply_case_mutation,
    )

    # A case counts as generic when its *primary* declared dictionary file --
    # the first entry of ``dict_file_relpaths`` -- is absent from the folder.
    # Core imposes no vocabulary on that mapping: whichever file a caller (or
    # the legacy default in ``core.compatibility``) declares first is the one
    # whose presence marks the folder as belonging to that solver. Declaring no
    # dictionary files at all leaves the folder generic.
    primary_relpaths = list(resolved_relpaths.values())[:1]
    generic_case = (
        solver_command is None
        and not resolved_overrides
        and not collect_patterns
        and not any((case_root / relpath).exists() for relpath in primary_relpaths)
    )

    return TutorialSpec(
        name=case_dir_name,
        case_root=case_root,
        case_mutation=dispatch_case_mutation,
        metadata={
            "notes": "Core generic case runner for arbitrary tutorial folders.",
            "workflow_dag": workflow_dag,
            "setup_root": str(setup_root),
            "output_dir": str(output_dir),
            "dict_file_relpaths": {
                key: str(value) for key, value in resolved_relpaths.items()
            },
            "run_script_relpath": str(run_script_path),
            "collect_patterns": list(collect_patterns),
            "has_default_dict_file_overrides": bool(resolved_overrides),
            "solver_command": list(solver_command) if not isinstance(solver_command, str) and solver_command is not None else solver_command,
            "pre_solve_commands": list(pre_solve_commands or ()),
            "dimension": dimension,
            "parallel": parallel,
            "touch_case_foam": touch_case_foam,
            "generic_case": generic_case,
        },
    )


def make_generic_case_spec(**kwargs: Any) -> TutorialSpec:
    """Solver-neutral alias used by registry case-folder discovery."""

    return make_spec(**kwargs)
