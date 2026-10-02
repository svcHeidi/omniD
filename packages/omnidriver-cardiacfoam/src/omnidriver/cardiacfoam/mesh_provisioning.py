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
