#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     heart_solver_comparison
#
# Description
#     Compares whole solver stacks (eikonal / monodomain / monodomain-eikonal
#     / bidomain) against ONE shared real heart anatomy (mesh + Purkinje
#     graph + material fields), held fixed in tutorials/heartSim3D-1D/
#     eikonalHeart -- reused in place per the owner's own instruction,
#     not duplicated. Each variant's config lives as a complete template
#     under that case's setup/solverVariants/<variant>/ (electroProperties,
#     fvSchemes, fvSolution, controlDict), since the differences between
#     solver stacks are whole structural blocks (different fields solved,
#     different coupler, different numerics), not small deltas -- the
#     apply_electro_property_overrides patch mechanism used elsewhere this
#     session cannot add or remove whole sub-dictionaries, only tweak
#     existing keys. Selector-driven synthesis (dict_builder.
#     build_electro_properties) was considered but rejected: nothing in
#     this codebase's own test suite has ever exercised it for a combined
#     myocardium + conductionNetworkDomains + domainCouplings + ecgDomains
#     configuration, an untested combination not worth risking here.
#
#     This is the catalog/registry the owner asked for: HEART_SOLVER_VARIANTS
#     names the four studies; each maps to a fixed template directory whose
#     four files apply_case swaps into constant/ and system/ verbatim.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Final

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.openfoam.parallel_execution import solve_steps
from omnidriver.core.specs.paths import resolve_spec_paths
from omnidriver.cardiacfoam.overrides import PLUGIN_ID, commit_case_overrides
from omnidriver.openfoam.utils import plan_verbatim_content

# The owner's four named studies -- each key is a directory name under
# <case_root>/setup/solverVariants/. Adding a fifth study means adding a
# fifth template directory (four files: electroProperties, fvSchemes,
# fvSolution, controlDict) and a fifth entry here; nothing else changes.
HEART_SOLVER_VARIANTS: Final[tuple[str, ...]] = (
    "eikonal",
    "monodomain",
    "monodomain-eikonal",
    "bidomain",
)

_TEMPLATE_FILES: Final[tuple[str, ...]] = (
    "electroProperties",
    "fvSchemes",
    "fvSolution",
    "controlDict",
)

_DEFAULT_CASE_DIR_NAME: Final[str] = "heartSim3D-1D/eikonalHeart"


def _validate_variant(solver_variant: str) -> None:
    if solver_variant not in HEART_SOLVER_VARIANTS:
        known = ", ".join(HEART_SOLVER_VARIANTS)
        raise ValueError(f"solver_variant must be one of: {known}; got {solver_variant!r}")


def _template_dir(case_root: Path, solver_variant: str) -> Path:
    return case_root / "setup" / "solverVariants" / solver_variant


def _build_cases(*, solver_variant: str) -> list[CaseConfig]:
    return [CaseConfig(case_id=solver_variant, params={"solver_variant": solver_variant})]


#: Where each template file lands under `case_root`. `electroProperties` is
#: the only one under `constant/`; the other three are under `system/` --
#: matching `_apply_case`'s own pre-Task-7 hardcoded destinations exactly.
_DESTINATION_RELPATH: Final[dict[str, str]] = {
    "electroProperties": "constant/electroProperties",
    "fvSchemes": "system/fvSchemes",
    "fvSolution": "system/fvSolution",
    "controlDict": "system/controlDict",
}


def _apply_case(case_root: Path, case: CaseConfig) -> None:
    """`TutorialSpec.apply_case` -- thin wrapper over `_plan_case` (Phase 3
    Task 7, following Task 6's own convention for the other eleven
    tutorials). `TutorialSpec.apply_case` has no default
    (`core/runtime/models.py`), so `make_spec` still supplies one regardless
    of `plan_case`; `invoke_case_mutation` prefers `plan_case` unconditionally
    once a spec supplies one, so this exists only for a caller that still
    invokes `apply_case` directly (e.g. this tutorial's own characterization
    test).
    """
    _plan_case(case_root, case)


def _plan_case(case_root: Path, case: CaseConfig):
    """`TutorialSpec.plan_case` (Phase 3 Task 7).

    Four whole template files, swapped in verbatim -- no key/value edit at
    all. Classified as a `RenderedFile` (`plan_verbatim_content`), not a
    source artifact: see that function's own docstring for the argument from
    how these documents are used downstream (cardiacFoam reads each one
    exactly as it reads any other tutorial's `electroProperties`/
    `controlDict`, so they belong in the channel's own audit trail, not
    referenced from outside it). `source_artifacts` names which
    solver-variant template supplied the bytes, since this request assigns no
    `ParameterAssignment` for `resolve_patch_mutation` to describe otherwise
    -- see `CaseMutationRequest`'s 2026-09-23 (Task 7) correction.
    """
    solver_variant = str(case.params["solver_variant"])
    template_dir = _template_dir(case_root, solver_variant)
    targets = tuple(
        plan_verbatim_content(
            _DESTINATION_RELPATH[name],
            (template_dir / name).read_text(encoding="utf-8"),
        )
        for name in _TEMPLATE_FILES
    )
    return commit_case_overrides(
        case_root,
        extra_targets=targets,
        extra_effects=tuple(
            f"replace {relpath} with the {solver_variant!r} template"
            for relpath in _DESTINATION_RELPATH.values()
        ),
        source_artifacts=(f"heart_solver_comparison.solverVariants:{solver_variant}",),
        workflow="heart_solver_comparison",
        requested_by="cardiacfoam.tutorials.heart_solver_comparison",
    )


def make_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = _DEFAULT_CASE_DIR_NAME,
    setup_dir_name: str | None = "setup",
    output_dir_name: str | None = None,
    solver_variant: str = "eikonal",
    run_in_parallel: bool = False,
) -> TutorialSpec:
    _validate_variant(solver_variant)

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=f"sweepRun_{solver_variant}",
    )

    steps, _final_id = solve_steps(
        solve_id="solve",
        solve_command="cardiacFoam",
        depends_on=[],
        run_in_parallel=run_in_parallel,
        case_root=case_root,
    )

    return TutorialSpec(
        name=f"heartSolverComparison-{solver_variant}",
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=partial(_build_cases, solver_variant=solver_variant),
        apply_case=_apply_case,
        plan_case=_plan_case,
        metadata={
            "notes": "Solver-stack comparison over one shared real heart anatomy.",
            "workflow_dag": {"steps": steps},
            "solver_variant": solver_variant,
            "run_in_parallel": run_in_parallel,
        },
    )
