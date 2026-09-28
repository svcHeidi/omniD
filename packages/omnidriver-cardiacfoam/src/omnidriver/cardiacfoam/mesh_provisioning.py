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

"""Which myocardiumSolver values need mesh provisioning outside the generic
`dx`-derived default. `electroModel.C` requires a real `fvMesh` regardless of
solver (`electroModel.C:344`), so every solver meshes: a `system/blockMeshDict`
with `blockMesh` run by the generated `Allrun` before the solver.
"""

from __future__ import annotations

#: No real spatial geometry to size a mesh from, so it gets a fixed one-cell
#: `blockMeshDict` (`single_cell_block_mesh_dict_text`) instead of the
#: `dx`-derived default the other solvers use.
SINGLE_CELL_SOLVERS = frozenset({"singleCellSolver"})
