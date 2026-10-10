"""The weights of the shared error norm: cell volumes for a finite-volume solver, lumped nodal control volumes
for a finite-element one."""
from __future__ import annotations

from typing import Sequence

from .problem import ProblemError


def cell_volume_weights(cells_per_axis: int, dimension: int, edge: float) -> list[float]:
    """The volume of each cell of a uniform ``cells_per_axis``**``dimension`` grid on a cube of side ``edge``
    (every cell the same)."""
    if cells_per_axis < 1 or dimension < 1 or edge <= 0:
        raise ProblemError("a grid needs at least one cell, one dimension and a positive edge", code="weights_invalid")
    return [(edge / cells_per_axis) ** dimension] * cells_per_axis ** dimension


def nodal_control_volumes(points: Sequence[Sequence[float]], elements: Sequence[Sequence[int]],
                          length_scale: float = 1.0) -> list[float]:
    """The lumped nodal control volume of each point of a structured line, quadrilateral or hexahedral mesh: each
    element's volume shared equally among its nodes (1/2 per node of a line, 1/4 of a quadrilateral, 1/8 of a
    hexahedron), so a node of a regular grid weighs one cell, halved once for each coordinate on which it lies on
    the boundary (in 2D a corner, edge and interior node weigh 1/4, 1/2 and 1 of a cell).

    An element's volume is the product of its bounding-box extents over the axes it spans; an axis on which it has
    no extent (a line's y and z, a quadrilateral's z) contributes a factor of 1. Coordinates are divided by
    ``length_scale`` to reach the problem's units. :class:`ProblemError` for an element naming a missing point."""
    weights = [0.0] * len(points)
    for ids in elements:
        if not ids or min(ids) < 0 or max(ids) >= len(points):
            raise ProblemError(f"an element names a point outside the {len(points)} given: {list(ids)}",
                               code="weights_invalid")
        volume = 1.0
        for axis in range(max(len(point) for point in points)):
            coordinates = [points[i][axis] for i in ids]
            extent = (max(coordinates) - min(coordinates)) / length_scale
            volume *= extent if extent > 0 else 1.0
        for i in ids:
            weights[i] += volume / len(ids)
    return weights
