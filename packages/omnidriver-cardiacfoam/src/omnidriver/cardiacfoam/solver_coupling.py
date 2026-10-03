"""Cross-domain solver coupling rules: which ``myocardiumSolver`` x ``purkinjeSolver`` x ``required_coupler`` combinations are valid, and why the invalid ones are forbidden.

Kept apart from ``ionic_model_catalog.py`` because the rules concern solver compatibility, not any ionic model."""
from __future__ import annotations

from typing import Final


SOLVER_COMPATIBILITY_RULES: Final[tuple[dict, ...]] = (
    {
        "myocardium_solver": "monodomainSolver",
        "purkinje_solver": "monodomain1DSolver",
        "required_coupler": "reactionDiffusionPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "eikonalSolver",
        "purkinje_solver": "eikonalSolver1D",
        "required_coupler": "eikonalPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "eikonalSolver",
        "purkinje_solver": "restitutionEikonalSolver1D",
        "required_coupler": "eikonalPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "monodomainSolver",
        "purkinje_solver": "eikonalSolver",
        "required_coupler": None,
        "valid": False,
        "reason": "Incompatible physics: reaction-diffusion myocardium cannot couple to eikonal Purkinje",
    },
    {
        "myocardium_solver": "monodomainSolver",
        "purkinje_solver": "eikonalSolver1D",
        "required_coupler": "eikonalMonodomainPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "monodomainSolver",
        "purkinje_solver": "restitutionEikonalSolver1D",
        "required_coupler": "eikonalMonodomainPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "eikonalSolver",
        "purkinje_solver": "monodomain1DSolver",
        "required_coupler": None,
        "valid": False,
        "reason": "Incompatible physics: eikonal myocardium cannot couple to reaction-diffusion Purkinje",
    },
    {
        "myocardium_solver": "bidomainSolver",
        "purkinje_solver": "monodomain1DSolver",
        "required_coupler": "reactionDiffusionPvjCoupler",
        "valid": True,
    },
    {
        "myocardium_solver": "bidomainSolver",
        "purkinje_solver": "*",
        "required_coupler": None,
        "valid": False,
        "reason": "bidomainSolver only supports reaction-diffusion coupling",
    },
    {
        "myocardium_solver": "singleCellSolver",
        "purkinje_solver": "*",
        "required_coupler": None,
        "valid": False,
        "reason": "singleCellSolver has no PDE domain; Purkinje coupling not applicable",
    },
)
