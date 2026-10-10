"""The norm's weights on regular grids whose control volumes are known by hand."""
from __future__ import annotations

import itertools
import math

import pytest

from omnidriver.verifier.problem import ProblemError
from omnidriver.verifier.weights import cell_volume_weights, nodal_control_volumes, tetrahedron_nodal_volumes

SCALE = 1000.0


def _grid(dimension: int, n: int, edge: float = 1000.0):
    """A regular mesh of the cube [0, edge]^dimension: points padded to three coordinates, one element (its node
    ids, any order) per cell."""
    h = edge / n
    index = {ijk: k for k, ijk in enumerate(itertools.product(range(n + 1), repeat=dimension))}
    points = [tuple(c * h for c in ijk) + (0.0,) * (3 - dimension) for ijk in index]
    elements = [[index[tuple(base[a] + corner[a] for a in range(dimension))] for corner in
                 itertools.product((0, 1), repeat=dimension)]
                for base in itertools.product(range(n), repeat=dimension)]
    return index, points, elements


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_corner_edge_and_interior_nodes_weigh_a_halving_fraction_of_a_cell(dimension):
    n = 4
    index, points, elements = _grid(dimension, n)
    weights = nodal_control_volumes(points, elements, SCALE)
    cell = (1.0 / n) ** dimension
    for ijk, k in index.items():
        on_boundary = sum(c in (0, n) for c in ijk)
        assert weights[k] == pytest.approx(cell / 2 ** on_boundary)


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_weights_sum_to_the_domain_volume(dimension):
    _, points, elements = _grid(dimension, 5)
    assert math.fsum(nodal_control_volumes(points, elements, SCALE)) == pytest.approx(1.0)


def test_the_scale_takes_the_mesh_to_the_problems_units():
    _, points, elements = _grid(2, 3, edge=2.0)
    assert math.fsum(nodal_control_volumes(points, elements, 2.0)) == pytest.approx(1.0)


def test_a_cell_volume_weight_is_the_cell_volume_and_they_sum_to_the_domain():
    weights = cell_volume_weights(8, 3, 1.0)
    assert len(weights) == 512 and weights[0] == pytest.approx(1 / 512)
    assert math.fsum(cell_volume_weights(5, 2, 2.0)) == pytest.approx(4.0)


def test_an_element_naming_a_missing_point_is_refused():
    with pytest.raises(ProblemError) as caught:
        nodal_control_volumes([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [[0, 2]])
    assert caught.value.code == "weights_invalid"


def _kuhn_tetrahedra(n: int, edge: float = 1000.0):
    """The cube [0, edge]^3 split into n^3 cubes of six tetrahedra each (the Kuhn split along the main diagonal),
    half of them listed with the opposite orientation."""
    index, points, _ = _grid(3, n, edge)
    paths = list(itertools.permutations(range(3)))
    elements = []
    for base in itertools.product(range(n), repeat=3):
        for p, order in enumerate(paths):
            corner, tet = list(base), [index[tuple(base)]]
            for axis in order:
                corner[axis] += 1
                tet.append(index[tuple(corner)])
            elements.append(tet if p % 2 else tet[::-1])
    return points, elements


def test_a_tetrahedron_gives_each_node_a_quarter_of_its_volume():
    points = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 4.0)]
    assert tetrahedron_nodal_volumes(points, [[0, 1, 2, 3]]) == pytest.approx([1.0] * 4)
    assert tetrahedron_nodal_volumes(points, [[0, 2, 1, 3]]) == pytest.approx([1.0] * 4)


def test_tetrahedral_weights_sum_to_the_domain_volume_whatever_the_orientation():
    points, elements = _kuhn_tetrahedra(3)
    weights = tetrahedron_nodal_volumes(points, elements, SCALE)
    assert len(elements) == 6 * 27 and math.fsum(weights) == pytest.approx(1.0)
    assert min(weights) > 0


@pytest.mark.parametrize("element", [[0, 1, 2], [0, 1, 2, 4]])
def test_a_tetrahedron_that_is_not_four_points_of_the_mesh_is_refused(element):
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    with pytest.raises(ProblemError) as caught:
        tetrahedron_nodal_volumes(points, [element])
    assert caught.value.code == "weights_invalid"


def test_a_flat_tetrahedron_is_refused():
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    with pytest.raises(ProblemError) as caught:
        tetrahedron_nodal_volumes(points, [[0, 1, 2, 3]])
    assert caught.value.code == "weights_invalid"
