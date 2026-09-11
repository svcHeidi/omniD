"""CLI-only tutorial descriptors.

This module stays for CLI consumers (``introspection.py``, ``listVerifiers``,
``listIonicModels``). New automation should prefer Run documents; see
``schemas/run-document.json`` and the ``RunDocument`` model in
``omnidriver.core.runtime.run_model``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .runtime.models import TutorialSpec
from .plugin_profile import is_environment_role

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


def _existing_relpaths(case_root: Path, candidates: tuple[str, ...]) -> list[str]:
    existing: list[str] = []
    for relpath in candidates:
        if (case_root / relpath).exists():
            existing.append(relpath)
    return existing


def _unique_case_param_values(spec: TutorialSpec, key: str) -> list[Any]:
    values = []
    seen: set[str] = set()
    for case in spec.build_cases():
        if key not in case.params:
            continue
        value = case.params[key]
        marker = repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        values.append(value)
    return values


def _case_parameter_contract(spec: TutorialSpec) -> dict[str, list[Any]]:
    cases = spec.build_cases()
    if not cases:
        return {}

    keys = sorted({key for case in cases for key in case.params})
    return {
        key: _unique_case_param_values(spec, key)
        for key in keys
    }


def describe_tutorial_contract(
    spec: TutorialSpec,
    *,
    resolution: str,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    case_root = spec.case_root
    # Split on the profile's own ``role``, not on a path prefix: the prefix
    # would make core re-derive plugin semantics from a string, and would
    # misfile a plugin-owned dictionary that happens to live under system/
    # (or a required initial-condition file that does not).
    # ``is_environment_role`` rather than a literal ``openfoam.`` prefix: the
    # escape tier admits other environments, and a FEniCS plugin's
    # ``x-fenics.mesh_file`` is environment-owned in exactly the sense this
    # split means. A prefix test files it under core's own required inputs.
    required_rules = driver_context.capabilities.case_files.required_rules()
    core_required_files = tuple(
        rule.path for rule in required_rules
        if not is_environment_role(rule.role)
    )
    solver_required_files = tuple(
        rule.path for rule in required_rules
        if is_environment_role(rule.role)
    )
    conditional_files = tuple(
        driver_context.capabilities.case_files.conditional_files()
    )
    declared_files = tuple(
        rule.path for rule in driver_context.capabilities.case_files.all_rules()
    )

    return {
        "name": spec.name,
        "resolution": resolution,
        "case_root": str(case_root),
        "setup_root": str(spec.setup_root),
        "output_dir": str(spec.output_dir),
        "core_required_files": _existing_relpaths(case_root, core_required_files),
        "solver_required_files": _existing_relpaths(case_root, solver_required_files),
        "conditional_files": _existing_relpaths(case_root, conditional_files),
        "declared_files": _existing_relpaths(case_root, declared_files),
        # These legacy fields remain for API compatibility. Their former
        # values were OpenFOAM-specific discovery; adapters that own mesh,
        # reference, or post-processing semantics must report them through a
        # dedicated adapter capability rather than Core guessing by filename.
        "mesh_files": [],
        "constant_files": [],
        "system_files": [],
        "reference_cases": [],
        "postprocess_modules": [],
        "case_parameters": _case_parameter_contract(spec),
        "metadata": spec.metadata,
    }
