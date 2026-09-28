"""cardiacFoam-specific strict-planning policy decisions."""

from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.detection import (
    detect_myocardium_solver_name,
    detect_verification_model_type,
)
from omnidriver.cardiacfoam.physics_layout import region_document


def is_nondimensional_case(spec) -> bool:
    """Plugin-contract hook exempting single-cell and manufactured-solution cases
    from the mesh-scale check.

    Only ``KeyError`` from the solver-name/verification-model detectors is
    swallowed; ``region_document`` raises ``PhysicsLayoutError`` for anything
    else it can't resolve, and that propagates.
    """
    electro_path = region_document(Path(spec.case_root), "electro", "electroProperties")
    if electro_path is None:
        return False
    try:
        return (
            detect_myocardium_solver_name(electro_path) == "singleCellSolver"
            or detect_verification_model_type(electro_path) is not None
        )
    except KeyError:
        return False
