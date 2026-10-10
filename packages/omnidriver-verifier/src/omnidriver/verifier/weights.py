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
    axes = max((len(point) for point in points), default=0)
    for ids in elements:
        if not ids or min(ids) < 0 or max(ids) >= len(points):
            raise ProblemError(f"an element names a point outside the {len(points)} given: {list(ids)}",
                               code="weights_invalid")
        volume = 1.0
        for axis in range(axes):
            coordinates = [points[i][axis] for i in ids]
            extent = (max(coordinates) - min(coordinates)) / length_scale
            volume *= extent if extent > 0 else 1.0
        for i in ids:
            weights[i] += volume / len(ids)
    return weights


def tetrahedron_nodal_volumes(points: Sequence[Sequence[float]], elements: Sequence[Sequence[int]],
                              length_scale: float = 1.0) -> list[float]:
    """The lumped nodal control volume of each point of a linear tetrahedral mesh: each tetrahedron's volume
    (|det|/6 of its edge vectors) shared equally among its four nodes, the row sum of the P1 mass matrix.
    Coordinates are divided by ``length_scale``. :class:`ProblemError` for an element that is not four points of
    the mesh, or has no volume."""
    weights = [0.0] * len(points)
    for ids in elements:
        if len(ids) != 4 or min(ids) < 0 or max(ids) >= len(points):
            raise ProblemError(f"a tetrahedron is four of the {len(points)} given points, not {list(ids)}",
                               code="weights_invalid")
        p0, p1, p2, p3 = ([c / length_scale for c in points[i]] for i in ids)
        a, b, c = ([q[k] - p0[k] for k in range(3)] for q in (p1, p2, p3))
        det = (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
               + a[2] * (b[0] * c[1] - b[1] * c[0]))
        if det == 0:
            raise ProblemError(f"the tetrahedron {list(ids)} has no volume", code="weights_invalid")
        for i in ids:
            weights[i] += abs(det) / 24
    return weights
