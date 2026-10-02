"""Case-model resolution and the sampling field names each resolved ionic and active-tension model exposes."""

from __future__ import annotations

from pathlib import Path

# Fixed fields the cardiac solvers expose regardless of the ionic /
# active-tension model. Model-specific names come from the catalogs.
_ELECTRO_SOLVER_FIELDS = ("Vm", "activationTime", "Iion", "phiE", "phiI")

# Active-tension / electromechanics coupling fields -- this repo's own
# catalog, always available regardless of build configuration.
_SOLID_SOLVER_FIELDS = ("Ta", "lambda")


def resolve_case_models(case_root: str | Path) -> dict[str, str | None]:
    """Best-effort resolution from ``constant/electroProperties``. Never raises;
    any of the three values may be ``None`` when the file or entry is absent."""
    from omnidriver.cardiacfoam.detection import (
        detect_active_tension_model_name,
        detect_ionic_model_name,
        detect_myocardium_solver_name,
    )

    electro_path = Path(case_root) / "constant" / "electroProperties"
    if not electro_path.exists():
        return {"solver": None, "ionic_model": None, "active_tension": None}
    resolved: dict[str, str | None] = {}
    for key, detect in (
        ("solver", detect_myocardium_solver_name),
        ("ionic_model", detect_ionic_model_name),
        ("active_tension", detect_active_tension_model_name),
    ):
        try:
            resolved[key] = detect(electro_path)
        except (OSError, KeyError):
            resolved[key] = None
    return resolved


def samplable_fields(resolved: dict[str, str | None]) -> dict[str, tuple[str, ...]]:
    """Field names the resolved cardiac model exposes, by region."""
    from omnidriver.cardiacfoam.active_tension_catalog import (
        ACTIVE_TENSION_MODEL_CATALOG,
    )
    from omnidriver.cardiacfoam.ionic_model_catalog import (
        IONIC_MODEL_CATALOG,
    )

    electro = set(_ELECTRO_SOLVER_FIELDS)
    ionic_entry = IONIC_MODEL_CATALOG.get(resolved.get("ionic_model") or "")
    if ionic_entry is not None:
        electro.update(ionic_entry.states)
        electro.update(ionic_entry.algebraic)
        electro.update(ionic_entry.recommended_exports)

    solid: set[str] = set()
    # An active-tension model is the only available signal for electromechanical
    # coupling: a spatial EP solver alone does not imply a mechanics region, and
    # a passive-only mechanics case (no active contraction) would be missed.
    active_tension = resolved.get("active_tension")
    solver = resolved.get("solver")
    has_solid_region = (
        active_tension is not None
        and solver is not None
        and solver != "singleCellSolver"
    )
    if has_solid_region:
        solid.update(_SOLID_SOLVER_FIELDS)
        at_entry = ACTIVE_TENSION_MODEL_CATALOG.get(active_tension or "")
        if at_entry is not None:
            solid.update(at_entry.states)
            solid.update(at_entry.algebraic)

    return {"electro": tuple(sorted(electro)), "solid": tuple(sorted(solid))}
