"""cardiacFoam-specific strict-planning policy decisions."""

from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.detection import (
    detect_myocardium_solver_name,
    detect_verification_model_type,
)
from omnidriver.cardiacfoam.physics_layout import region_document


def is_nondimensional_case(spec) -> bool:
    """Corrected 2026-09-26 (spec 2026-09-26 A7): this read only
    ``constant/electroProperties``, so a region-split case such as
    ``monodomainTotalLagrangianEM`` was missed, and core's name rule hid it.
    The electro region now comes from ``physics_layout``."""
    try:
        electro_path = region_document(Path(spec.case_root), "electro", "electroProperties")
        if electro_path is None:
            return False
        return (
            detect_myocardium_solver_name(electro_path) == "singleCellSolver"
            or detect_verification_model_type(electro_path) is not None
        )
    except Exception:
        return False
