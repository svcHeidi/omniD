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
#     Which myocardiumSolver values have no real spatial geometry, for
#     dict_builder's mesh decisions.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""electroModel.C requires a real fvMesh regardless of solver
(`refCast<const fvMesh>(mesh())` at electroModel.C:344) -- even
singleCellSolver needs one. Every solver therefore meshes the same way: a
`system/blockMeshDict`, written by `dict_builder.build_case`/
`resolve_synthesis_mutation`, with `blockMesh` run by the generated `Allrun`
before the solver.

`SINGLE_CELL_SOLVERS` has no real spatial geometry to size a mesh from, so it
gets a fixed one-cell `blockMeshDict`
(`omnidriver.openfoam.mesh_provisioning.single_cell_block_mesh_dict_text`)
instead of the `dx`-derived generic default the other solvers use.

**Corrected 2026-09-28 (owner decision):** this module used to instead copy a
bundled static 1-cell `constant/polyMesh` fixture for `singleCellSolver`
directly (`provision_mesh`/`meshless_polymesh_fixture`), skipped whenever
`dry_run=True` -- and `sweep.py::materialize_case` always passes
`dry_run=True`, so a from-scratch single-cell sweep case got no mesh at all.
`singleCellSolver` now meshes exactly like every other solver instead: a
`blockMeshDict` in the plan (never `dry_run`-gated, same as the other
solvers') and `blockMesh` in `Allrun`.
"""

from __future__ import annotations

SINGLE_CELL_SOLVERS = frozenset({"singleCellSolver"})
