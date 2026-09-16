"""Solver-neutral generic case spec implementation.

This module owns the default case-folder execution contract. Environment
adapters declare the case entrypoint and output convention; plugins may still
call this factory for richer flows such as build-and-launch.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from omnidriver.core.specs.common import (
    resolve_run_script_path,
    resolve_spec_paths,
)

from .models import CaseConfig, TutorialSpec
from omnidriver.core.plugin_profile import entrypoint_command

# Resolve the bundled runner from the installed package.
RUN_CASE_SCRIPT_RELPATH = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "run_case.sh"
)


DictFileOverrides = Mapping[str, "Mapping[str, Any] | Sequence[Mapping[str, Any]]"]


def _merged_dict_file_overrides(
    item: Mapping[str, Any],
    default_overrides: Mapping[str, Any],
) -> dict[str, Any]:
    """Per-case ``dict_file_overrides``, falling back to the spec-level default.

    A case entry may name only some of the dictionary files; the remaining ones
    keep whatever the spec-level default declared for them.
    """
    merged = dict(default_overrides)
    merged.update(item.get("dict_file_overrides") or {})
    return {key: value for key, value in merged.items() if value}


def _normalize_case_specs(
    *,
    cases: Sequence[Mapping[str, Any]] | None,
    dict_file_overrides: Mapping[str, Any],
    dimension: str | None,
    parallel: bool,
    touch_case_foam: bool,
    explicit_bashrc: str | Path | None,
    solver_command: str | Sequence[str] | None,
    pre_solve_commands: Sequence[str | Sequence[str]],
) -> list[CaseConfig]:
    if cases is None:
        payload = {
            "dict_file_overrides": dict(dict_file_overrides),
            "dimension": dimension,
            "parallel": parallel,
            "touch_case_foam": touch_case_foam,
            "explicit_bashrc": str(explicit_bashrc) if explicit_bashrc is not None else None,
            "solver_command": solver_command,
            "pre_solve_commands": list(pre_solve_commands),
        }
        return [CaseConfig(case_id="default", params=payload)]

    normalized: list[CaseConfig] = []
    for index, item in enumerate(cases, start=1):
        case_id = str(item.get("case_id", f"case{index:03d}"))
        item_bashrc = item.get("explicit_bashrc")
        normalized.append(
            CaseConfig(
                case_id=case_id,
                params={
                    "dict_file_overrides": _merged_dict_file_overrides(
                        item, dict_file_overrides,
                    ),
                    "dimension": item.get("dimension", dimension),
                    "parallel": bool(item.get("parallel", parallel)),
                    "touch_case_foam": bool(item.get("touch_case_foam", touch_case_foam)),
                    "explicit_bashrc": (
                        str(item_bashrc)
                        if item_bashrc is not None
                        else (str(explicit_bashrc) if explicit_bashrc is not None else None)
                    ),
                    "solver_command": item.get("solver_command", solver_command),
                    "pre_solve_commands": list(item.get("pre_solve_commands", pre_solve_commands)),
                },
            )
        )
    return normalized


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    dict_file_relpaths: Mapping[str, Path],
    mutation_callback,
) -> None:
    mutation_callback(
        case_root,
        case,
        dict_file_relpaths=dict(dict_file_relpaths),
        dict_file_overrides=dict(case.params.get("dict_file_overrides") or {}),
    )


def _split_command(command: str | Sequence[str]) -> list[str]:
    return command.split() if isinstance(command, str) else list(command)


def _workflow_dag_for(
    *,
    solver_command: str | Sequence[str] | None,
    pre_solve_commands: Sequence[str | Sequence[str]],
    driver_context: Any | None = None,
) -> dict[str, Any]:
    """Build the workflow DAG for a generic case.

    With no ``solver_command`` the whole run is one step invoking the case's
    entrypoint. That entrypoint is the plugin's declared
    environment's declared entrypoint, not a hardcoded script name. A plugin
    naming its entrypoint anything else therefore gets a matching DAG.
    """
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
    cases: Sequence[Mapping[str, Any]] | None = None,
    dimension: str | None = None,
    parallel: bool = False,
    touch_case_foam: bool = False,
    explicit_bashrc: str | Path | None = None,
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

    normalized_cases = _normalize_case_specs(
        cases=cases,
        dict_file_overrides=resolved_overrides,
        dimension=dimension,
        parallel=parallel,
        touch_case_foam=touch_case_foam,
        explicit_bashrc=explicit_bashrc,
        solver_command=solver_command,
        pre_solve_commands=normalized_pre_solve,
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
        and cases is None
        and not resolved_overrides
        and not collect_patterns
        and not any((case_root / relpath).exists() for relpath in primary_relpaths)
    )

    return TutorialSpec(
        name=case_dir_name,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=lambda: list(normalized_cases),
        apply_case=partial(
            _apply_case,
            dict_file_relpaths=resolved_relpaths,
            mutation_callback=_apply_case_mutation,
        ),
        metadata={
            "notes": "Core generic case runner for arbitrary tutorial folders.",
            "workflow_dag": workflow_dag,
            "dict_file_relpaths": {
                key: str(value) for key, value in resolved_relpaths.items()
            },
            "run_script_relpath": str(run_script_path),
            "collect_patterns": list(collect_patterns),
            "case_count": len(normalized_cases),
            "has_default_dict_file_overrides": bool(resolved_overrides),
            "solver_command": list(solver_command) if not isinstance(solver_command, str) and solver_command is not None else solver_command,
            "pre_solve_commands": list(pre_solve_commands or ()),
            "generic_case": generic_case,
        },
    )


def make_generic_case_spec(**kwargs: Any) -> TutorialSpec:
    """Solver-neutral alias used by registry case-folder discovery.

    Its ``_apply_case_mutation`` setdefault is gone: make_spec's own default is
    now the same no-op, so this alias no longer has to opt out of a cardiac
    default that no longer exists.
    """

    return make_spec(**kwargs)
