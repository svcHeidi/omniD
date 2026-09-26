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
    The electro region now comes from ``physics_layout``.

    Corrected 2026-09-26 (R1 fix, finding I1): this used to swallow every
    exception from ``region_document`` too (bare ``except Exception``), so
    an unknown physics type, a missing or malformed coupling document, or
    even a missing packaged ``physics_layout.json`` all silently answered
    "not exempt" -- one native case
    (``electrophysiologyProtocols/ionicHeterogeneity``) lost its mesh-scale
    exemption this way, with no error anywhere. ``region_document`` now
    raises ``physics_layout.PhysicsLayoutError`` (a ``TutorialRecordError``)
    for those, and it is left to propagate as a named refusal. Only the
    *detectors'* own parse of ``electroProperties``
    (``detect_myocardium_solver_name``, which raises ``KeyError`` when the
    active solver's ``<solver>Coeffs`` block is missing) is still swallowed
    here, exactly as it was before A7.
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
