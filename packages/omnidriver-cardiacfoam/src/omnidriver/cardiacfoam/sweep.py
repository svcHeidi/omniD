"""Historical cardiacFoam generic-sweep routing and materialization.

Why this exists
---------------
Generic sweep JSON originally targeted cardiacFoam's ``build_and_launch``
shape: electro/physics selectors, ``deltaT``/``endTime``, and the default
``dx`` mesh.  Plan 1 moves ownership behind the cardiac plugin without
changing that public format or any generated file.

Activation
----------
The selected plugin provides these hooks, or the Plan-1 compatibility adapter
uses them for a legacy plugin that lacks a sweep capability.

Compatibility
-------------
The existing sweep-routing, materialization, runner, and manifest suites pin
this behaviour.  Plan 2 may introduce a solver-neutral explicit-mutation sweep
format at this seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.openfoam.dict_builder import is_known_override_driver_path
from .dict_builder import (
    SELECTOR_KEYS,
    build_and_launch,
)


_SUPPORTED_CONTROL_DICT_KEYS: frozenset[str] = frozenset({"deltaT", "endTime"})
_NON_ROUTABLE_KEYS: frozenset[str] = frozenset({"caseId"})


def route_case_values(
    *,
    base: dict[str, Any],
    resolved_axis_values: dict[str, Any],
    driver_context,
) -> dict[str, Any]:
    catalog = driver_context.capabilities.dictionaries.catalog()
    control_dict_keys = frozenset(
        entry.driver_path for entry in catalog.entries_for("controlDict")
    )
    physics_selector_keys = frozenset(
        entry.driver_path for entry in catalog.entries_for("physicsProperties")
    )
    unsupported_control_dict_keys = control_dict_keys - _SUPPORTED_CONTROL_DICT_KEYS

    electro_selectors: dict[str, Any] = dict(base.get("electro_selectors", {}))
    physics_selectors: dict[str, Any] = dict(base.get("physics_selectors", {}))
    electro_overrides: dict[str, Any] = dict(base.get("electro_overrides", {}))
    physics_overrides: dict[str, Any] = dict(base.get("physics_overrides", {}))
    delta_t: Any = base.get("delta_t")
    end_time: Any = base.get("end_time")
    dx: Any = base.get("dx")

    for key, value in resolved_axis_values.items():
        if key in _NON_ROUTABLE_KEYS:
            continue
        if key in SELECTOR_KEYS:
            electro_selectors[key] = value
        elif key in physics_selector_keys:
            physics_selectors[key] = value
        elif key == "deltaT":
            delta_t = value
        elif key == "endTime":
            end_time = value
        elif key == "dx":
            dx = value
        elif key in unsupported_control_dict_keys:
            known = ", ".join(sorted(_SUPPORTED_CONTROL_DICT_KEYS))
            raise SweepValidationError(
                f"controlDict sweep axis '{key}' is not supported by this plan; "
                f"supported controlDict axes are: {known}"
            )
        elif is_known_override_driver_path(key, driver_context=driver_context):
            electro_overrides[key] = value
        else:
            raise SweepValidationError(
                f"sweep axis '{key}' is not a recognized selector, controlDict "
                "key, electroProperties/physicsProperties driver_path, or "
                "'dx' (mesh resolution for the generic default blockMeshDict); "
                "it would have no effect on the generated case."
            )

    return {
        "electro_selectors": electro_selectors,
        "physics_selectors": physics_selectors,
        "electro_overrides": electro_overrides,
        "physics_overrides": physics_overrides,
        "delta_t": delta_t,
        "end_time": end_time,
        "dx": dx,
    }


def materialize_case(*, case_dir: Path, routed: dict[str, Any]) -> None:
    """Write a runnable generic sweep case without any authored workflow metadata.

    The case root remains OpenFOAM-owned: dictionaries plus a hand-runnable
    ``Allrun`` only. Agent-visible execution intent/state is persisted later as
    driver-owned ``run_document.json`` and ``workflow_state.json`` under the
    sweep output tree.

    **Corrected 2026-09-24 (Phase 3 Task 10, bypass 5):** ``Allrun`` used to
    be written here with a bare ``write_text`` + ``chmod`` call, after
    ``build_and_launch`` had already committed everything else through the
    channel -- a second, unaudited write, and a second transaction for one
    case materialization (a failure between the two left a case with inputs
    but no runnable ``Allrun``). ``include_allrun=True`` folds it into the
    same plan ``build_and_launch`` commits in its one ``commit_case_write``
    call instead; see ``dict_builder.build_case``'s docstring for the exact
    body/mode rule.
    """
    build_and_launch(
        electro_selectors=routed["electro_selectors"],
        physics_selectors=routed["physics_selectors"],
        case_dir=case_dir,
        electro_overrides=routed["electro_overrides"] or None,
        physics_overrides=routed["physics_overrides"] or None,
        delta_t=routed["delta_t"],
        end_time=routed["end_time"],
        dx=routed.get("dx"),
        dry_run=True,
        overwrite=True,
        include_allrun=True,
    )
