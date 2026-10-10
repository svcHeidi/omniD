"""The numerics cardiacFOAM's own keys carry, attached to their menu values as the source and its authors state them.

Each claim is recorded as stated, with where it is stated, and ``settled_by`` is null until a run of ours settles it. What
the OpenFOAM schemes contribute (the ``ddt(Vm)`` scheme a step composes with) is the OpenFOAM layer's own data.
"""

from __future__ import annotations

from typing import Any, Final

_SRC = "src/electroModels/"
_DOMAIN = _SRC + "electroDomains/myocardiumDomain/"
_MONODOMAIN = _SRC + "myocardiumModels/monodomainSolver/monodomainSolver.C"
_BATCHED = "src/ionicModels/ionicModel/batchedIonicModel.H"


def _source(file: str, excerpt: str, reading: str) -> dict[str, Any]:
    return {"kind": "source", "file": file, "excerpt": excerpt, "reading": reading}


def _authors(ref: str) -> dict[str, Any]:
    return {"kind": "authors", "ref": ref}


def _claim(stated_by: list[dict[str, Any]], **attributes: Any) -> dict[str, Any]:
    return {**attributes, "stated_by": stated_by, "settled_by": None}


TIME_COUPLING_SCHEME: Final = {
    "godunov": _claim(
        [_authors("cardiacFOAM's description of timeCouplingScheme: godunov is first-order Lie splitting")],
        formal_order={"time": 1},
    ),
    "sbdf2": _claim(
        [
            _source(
                _DOMAIN + "myocardiumDomain.H", "Is there enough Iion history for the second-order source extrapolation?",
                "sbdf2 extrapolates the ionic current at the end of the step from its two previous levels",
            ),
            _source(
                _DOMAIN + "myocardiumDomain.C", "supports both second-order couplings",
                "the selection requires an ionic model that supports both second-order couplings",
            ),
            _source(
                _MONODOMAIN, "tIionExtrap = *IionOldPtr + r*(*IionOldPtr - *IionOldOldPtr);",
                "monodomainSolver::solveDiffusionImplicit solves fvm::ddt(Vm) against this extrapolated ionic current, so the "
                "step's time order is also bounded by the order of the ddt(Vm) scheme of fvSchemes",
            ),
            _authors("cardiacFOAM's description of timeCouplingScheme: sbdf2 is second-order semi-implicit backward differentiation"),
        ],
        formal_order={"time": 2},
        conditions=[
            "the second-order ionic-current extrapolation needs two previous levels (timeIndex >= 3); earlier steps use the "
            "ionic current at the current state",
            "the ionic model must support both Vm-rate coupling and ionic-current evaluation, or the run stops",
        ],
        composes="the time order of the step is the lower of this one and the order of the ddt(Vm) scheme in fvSchemes",
    ),
}

SOLUTION_ALGORITHM: Final = {
    "explicit": _claim(
        [
            _source(
                _MONODOMAIN, "== fvc::laplacian(tGf(), domain.Vm())",
                "monodomainSolver::solveDiffusionExplicit evaluates the diffusion term explicitly against fvm::ddt(Vm), "
                "whose scheme is the ddt(Vm) scheme of fvSchemes",
            ),
            _source(
                _DOMAIN + "myocardiumDomain.C", "explicit stability limit",
                "applyModelTimeControls caps deltaT at suggestExplicitDeltaT(maxCo) when the explicit algorithm is used",
            ),
            _authors("cardiacFOAM's description of solutionAlgorithm: an operator-split forward-Euler diffusion step"),
        ],
        stability={"deltaT": "capped at suggestExplicitDeltaT(maxCo); maxCo is read from controlDict, default 0.1"},
    ),
    "implicit": _claim(
        [
            _source(
                _MONODOMAIN, "== fvm::laplacian(tGf(), domain.Vm())",
                "monodomainSolver::solveDiffusionImplicit solves the diffusion term implicitly against fvm::ddt(Vm), "
                "whose scheme is the ddt(Vm) scheme of fvSchemes",
            ),
            _authors("cardiacFOAM's description of solutionAlgorithm: a pimple-controlled implicit solve"),
        ],
    ),
}

BATCHED_INTEGRATOR: Final = {
    "euler": _claim(
        [_source(
            _BATCHED, 'kernel.useExplicitEuler = integratorName_ == "euler";',
            "the integrator is the explicit Euler method; its first order is the method's, not a statement in the source",
        )],
        formal_order={"time": 1},
    ),
    "rushLarsen": _claim(
        [_source(
            _BATCHED, 'kernel.useRushLarsen = integratorName_ == "rushLarsen";',
            "a state takes the Rush-Larsen exponential update only where the model supplies its steady state and a time "
            "constant tau > 0; every other state takes the explicit Euler step; the source states no order",
        )],
        conditions=[
            "only the states whose model supplies Rush-Larsen parameters take the exponential update; the others take the explicit Euler step",
        ],
    ),
}
