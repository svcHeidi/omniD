"""Build the legacy RunDocument-v2 cardiac configuration from case files.

This is the unchanged electroProperties/physicsProperties parser formerly
embedded in core.  RunDocument v2 remains cardiac-shaped during Plan 1; Plan 2
may replace this capability with a solver-neutral v3 configuration contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from foamlib import FoamFile

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.openfoam.dict_builder import populate_values
from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES
from omnidriver.cardiacfoam.dict_builder import (
    build_electro_properties,
    build_physics_properties,
    parse_electro_properties,
    resolve_context,
    select_applicable_entries,
)
from omnidriver.cardiacfoam.own_context import own_driver_context
from omnidriver.core.specs.validation import primary_phase, slot_key

# This plugin owns its phase vocabulary; see CardiacFoamPlugin.get_phases().
_PHASES: tuple[str, ...] = ("anatomy", "physics", "stimulus", "solver")

#: Namespaced role the adapter's profile uses for its controlDict rule (see
#: ``plugin.yaml``'s ``case_profile.dictionaries``). Matched by role, not by
#: a literal ``system/controlDict`` path, so this stays correct if the
#: profile ever relocates the file -- the profile is the one place that fact
#: is allowed to live.
_CONTROL_DICT_ROLE = "openfoam.control_dict"


def _read_physics_type(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return str(FoamFile(path)["type"])
    except (KeyError, ValueError):
        return None


def _read_control_dict_values(
    case_root: Path, driver_context: Any,
) -> tuple[dict[str, str], tuple[StrictDiagnostic, ...]]:
    """Read the solver-phase values the case's controlDict actually carries.

    Resolved BY ROLE, never by literal path: the adapter declares
    ``openfoam.control_dict`` in its profile, and
    ``CardiacFoamPlugin.get_selected_start_time`` already resolves the same
    file the same way. Spelling ``system/controlDict`` here would be a
    second declaration of a fact the profile already owns.

    A key silently defaulted would make the RunDocument's ``config`` lie
    about what the run actually used -- ``build_control_dict`` takes
    ``delta_t``/``end_time``/``write_interval`` as parameters written into
    the case, so the case's own controlDict is the only source of truth for
    them. Every absence is reported, never defaulted.
    """
    diagnostics: list[StrictDiagnostic] = []
    values: dict[str, str] = {}

    rule = next(
        (
            r for r in driver_context.capabilities.case_files.all_rules()
            if r.role == _CONTROL_DICT_ROLE
        ),
        None,
    )
    if rule is None:
        diagnostics.append(diagnostic(
            "error",
            "missing_control_dict_role",
            f"No case_files rule in this plugin's profile declares role "
            f"{_CONTROL_DICT_ROLE!r}",
        ))
        return values, tuple(diagnostics)

    control_dict_path = case_root / rule.path
    if not control_dict_path.exists():
        diagnostics.append(diagnostic(
            "error",
            "missing_control_dict",
            f"Missing controlDict at {control_dict_path}",
            source=str(control_dict_path),
        ))
        return values, tuple(diagnostics)

    read_value = driver_context.capabilities.config_value.reader()

    for entry in CONTROL_DICT_ENTRIES:
        key = entry.driver_path
        value = read_value(control_dict_path, key)
        if value is None:
            diagnostics.append(diagnostic(
                "error",
                "missing_control_dict_value",
                f"Could not read {key!r} from {control_dict_path}",
                source=str(control_dict_path),
                field=key,
            ))
        else:
            values[key] = value

    return values, tuple(diagnostics)


def build_config(spec) -> tuple[dict[str, dict[str, Any]], tuple[StrictDiagnostic, ...]]:
    diagnostics: list[StrictDiagnostic] = []
    config: dict[str, dict[str, Any]] = {
        "anatomy": {},
        "physics": {},
        "stimulus": {},
        "solver": {},
    }
    case_root = Path(spec.case_root)
    generic_case = bool(spec.metadata.get("generic_case")) if spec.metadata else False
    if generic_case:
        return config, ()

    electro_path = case_root / "constant" / "electroProperties"
    physics_path = case_root / "constant" / "physicsProperties"
    physics_type = _read_physics_type(physics_path)
    if physics_type is None:
        diagnostics.append(diagnostic(
            "error",
            "missing_physics_properties",
            f"Could not read physicsProperties type from {physics_path}",
            source=str(physics_path),
            field="type",
        ))
    else:
        config["physics"]["type"] = physics_type
        try:
            build_physics_properties({"type": physics_type})
        except Exception as exc:
            diagnostics.append(diagnostic(
                "error", "invalid_physics_properties", str(exc), source=str(physics_path),
            ))

    if not electro_path.exists():
        diagnostics.append(diagnostic(
            "error",
            "missing_electro_properties",
            f"Missing electroProperties at {electro_path}",
            source=str(electro_path),
        ))
    else:
        try:
            parsed = parse_electro_properties(electro_path)
            selectors = parsed["selectors"]
            overrides = parsed.get("overrides", {})
            try:
                build_electro_properties(selectors, overrides=overrides or None)
            except Exception as exc:
                diagnostics.append(diagnostic(
                    "error", "invalid_electro_properties", str(exc), source=str(electro_path),
                ))
            context = resolve_context(selectors, overrides=overrides or None)
            applicable_entries = select_applicable_entries(context)
            populated = populate_values(applicable_entries, context)
            for entry_obj in applicable_entries:
                key = slot_key(entry_obj.driver_path)
                if entry_obj.dynamic_path and key not in context:
                    continue
                if key not in populated:
                    continue
                phase = primary_phase(entry_obj, _PHASES) or "physics"
                config[phase][key] = populated[key]
        except Exception as exc:
            diagnostics.append(diagnostic(
                "error", "unparseable_electro_properties", str(exc), source=str(electro_path),
            ))

    control_dict_values, control_dict_diagnostics = _read_control_dict_values(
        case_root, own_driver_context(),
    )
    config["solver"].update(control_dict_values)
    diagnostics.extend(control_dict_diagnostics)

    return config, tuple(diagnostics)
