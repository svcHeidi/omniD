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
#     plugins.cardiacfoam.mesh_provisioning
#
# Description
#     Chooses and provisions a mesh for a cardiacFoam case built from scratch
#     by build_and_launch, based on the case's myocardiumSolver.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""electroModel.C requires a real fvMesh regardless of solver
(`refCast<const fvMesh>(mesh())` at electroModel.C:344) -- even
singleCellSolver needs one, which is why the real singleCell tutorial ships a
static trivial 1-cell `constant/polyMesh/`. Neither `build_and_launch` nor
`sweep_runner.materialize_case` provisioned any mesh for a from-scratch
`case_folder` before this module existed.

`singleCellSolver` has no real spatial geometry: `provision_mesh` below copies
the bundled static 1-cell polyMesh fixture directly into `constant/polyMesh/`.

**Corrected 2026-09-24 (Phase 3 Task 10):** this docstring used to describe a
second strategy here too -- `monodomainSolver`/`bidomainSolver`/`eikonalSolver`
writing the generic default `system/blockMeshDict` via `provision_mesh`'s own
`BLOCK_MESH_SOLVERS` branch. Review R4 found that branch had zero production
callers (`ionic_catalog_verification.py`, the only real caller, hardcodes
`myocardium_solver="singleCellSolver"`), and `build_and_launch`'s own spatial
case-building had already moved to `dict_builder.build_case`'s own
`CaseWritePlan` (folding in `omnidriver.openfoam.mesh_provisioning`'s
`default_block_mesh_dict_text` directly, gated on `_block_mesh_solvers()`
membership -- see that module's docstring), same as this module's own header
comment already said for the meshless fixture. The dead branch is deleted;
`BLOCK_MESH_SOLVERS` itself stays, since `dict_builder._block_mesh_solvers()`
still reads it for that live decision.

`provision_mesh` today implements the one strategy above; the solver-neutral
half of the strategy this docstring used to also describe -- rendering the
default `blockMeshDict` and the `dx`-to-cell-count arithmetic -- always lived
in, and still lives in, `omnidriver.openfoam.mesh_provisioning`, called
directly by `dict_builder.build_case` rather than through this function.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SINGLE_CELL_POLYMESH_DIR = _FIXTURES_DIR / "single_cell_polymesh"

MESHLESS_SOLVERS = frozenset({"singleCellSolver"})
#: Not read by any code in this module since 2026-09-24 (Phase 3 Task 10
#: deleted `provision_mesh`'s own dead branch over it) -- kept because
#: `dict_builder._block_mesh_solvers()` still imports and reads it for
#: `build_case`'s live blockMeshDict decision.
BLOCK_MESH_SOLVERS = frozenset({"monodomainSolver", "bidomainSolver", "eikonalSolver"})

_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def provision_mesh(
    *, case_dir: Path, myocardium_solver: str, dx_m: float | None = None,
    dry_run: bool = False,
) -> bool:
    """Provision whatever mesh `myocardium_solver` needs under `case_dir`.

    Returns False: either the solver is in `MESHLESS_SOLVERS` and a concrete
    mesh was copied directly (or already present), or the solver is unknown
    to this function and mesh provisioning is left to the caller.

    **Corrected 2026-09-24 (Phase 3 Task 10):** this used to also return True
    for a `BLOCK_MESH_SOLVERS` member, having written a generic default
    `system/blockMeshDict` for it -- deleted as dead code (see the module
    docstring's own dated correction); this function can no longer return
    True. `dict_builder.build_case` is the live source of that same decision
    now (`needs_block_mesh = myocardium_solver in _block_mesh_solvers()`),
    and it is not this function's caller.

    Unlike `build_and_launch`'s other generated files, a mesh is never
    clobbered on a repeat call regardless of that call's own `overwrite`
    flag: re-materializing a case (e.g. a retried sweep-run case) should not
    wipe out an already-valid mesh, and a hand-authored custom
    blockMeshDict/polyMesh must never be silently replaced by this generic
    default.

    `dx_m` (metres) is meaningless for `MESHLESS_SOLVERS` (no spatial
    geometry at all) and rejected outright rather than silently having no
    effect, and it has no bearing on real anatomical meshes imported via
    `vtkUnstructuredToFoam`, which this function never touches.

    `dry_run` (2026-09-23, R3 finding 8): validation (the `dx_m` rejection
    above) still runs unconditionally -- a dry run that silently skipped it
    would let `build_and_launch(..., dry_run=True, dx=...)` claim success for
    a combination the real run would refuse. Only the filesystem effect below
    is skipped, so a dry run reports what it would do without writing a mesh.

    **Fixed 2026-09-23 (R3 finding 8, Task 12, batch P2-H):** the
    `MESHLESS_SOLVERS` skip guard used to be ``all(...)`` over the five
    polyMesh files, so a *partially* present hand-authored mesh (some but not
    all five) failed the guard and every one of the five was silently
    overwritten. A partial set now raises instead, for every caller of this
    function -- `build_and_launch` no longer calls this branch at all (its
    meshless-solver mesh is folded into `dict_builder.build_case`'s
    `CaseWritePlan` and committed through `commit_case_write`, which has its
    own precondition-based conflict detection); `provision_mesh` itself keeps
    this direct-copy strategy for its other caller,
    `ionic_catalog_verification.py`, which does not go through
    `build_and_launch`.
    """
    if myocardium_solver in MESHLESS_SOLVERS:
        if dx_m is not None:
            raise ValueError(
                f"dx has no effect for myocardiumSolver={myocardium_solver!r} "
                "(no spatial mesh -- it has no geometry for dx to resolve)."
            )
        poly_mesh_dir = case_dir / "constant" / "polyMesh"
        present = [name for name in _POLYMESH_FILES if (poly_mesh_dir / name).exists()]
        if present and len(present) != len(_POLYMESH_FILES):
            missing = [name for name in _POLYMESH_FILES if name not in present]
            raise ValueError(
                f"{poly_mesh_dir} has a partially authored mesh (present: "
                f"{present}, missing: {missing}); a previous version of this "
                f"function silently overwrote all five with the bundled "
                f"fixture whenever even one was missing (R3 finding 8) -- "
                f"refusing instead of guessing which provenance should win. "
                f"Author all five files by hand, or remove the partial set "
                f"before calling this again."
            )
        already_present = bool(present)
        if not already_present and not dry_run:
            poly_mesh_dir.mkdir(parents=True, exist_ok=True)
            for name in _POLYMESH_FILES:
                shutil.copyfile(_SINGLE_CELL_POLYMESH_DIR / name, poly_mesh_dir / name)
        return False

    # Unknown/future solver: leave mesh provisioning to the caller.
    return False


def meshless_polymesh_fixture() -> dict[str, str]:
    """The bundled single-cell polyMesh fixture's five files, by name.

    Text, not bytes: every file in this fixture is a small ASCII OpenFOAM
    list (``FoamFile`` header plus a handful of entries), and
    `ResolvedMutation`'s targets must be JSON-shaped -- `core.case_write.
    _freeze` refuses raw `bytes` outright, the same way a plan payload
    always has (only `RenderedFile.content`, outside this payload system,
    carries real bytes). `render_synthesis_case_files` already treats a
    string `content` target as text to `.encode()`, exactly like every
    other synthesis target (`build_electro_properties` and siblings).

    Exposed (Task 12, batch P2-H) so `dict_builder.resolve_synthesis_mutation`/
    `build_case` can fold this fixture into the case-write channel as
    ordinary `skip_if_present` synthesis targets, instead of `provision_mesh`
    copying it directly with `shutil.copyfile` and no journal. `provision_mesh`
    itself is unchanged as a standalone function -- it is still the right
    tool for `ionic_catalog_verification.py`, which does not go through
    `build_and_launch`.
    """
    return {name: (_SINGLE_CELL_POLYMESH_DIR / name).read_text() for name in _POLYMESH_FILES}
