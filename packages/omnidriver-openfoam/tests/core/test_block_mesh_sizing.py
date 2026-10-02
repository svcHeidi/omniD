"""The generic default blockMeshDict render and its dx arithmetic. Which solver
wants it, or a fixed one-cell mesh, is the solver package's decision."""

import re

import pytest

from omnidriver.openfoam.case_builder import default_block_mesh_dict_text
from omnidriver.openfoam.case_planning import cell_counts_from_dx


def _cell_counts(text: str) -> tuple[int, int, int]:
    match = re.search(r"hex \([^)]*\)\s*\((\d+)\s+(\d+)\s+(\d+)\)", text)
    assert match is not None, text
    return tuple(int(g) for g in match.groups())


def test_cell_counts_from_dx_divides_exactly():
    assert cell_counts_from_dx(0.001, (0.002, 0.002, 0.002)) == (2, 2, 2)
    assert cell_counts_from_dx(0.0004, (0.002, 0.002, 0.002)) == (5, 5, 5)


def test_cell_counts_from_dx_rejects_non_exact_division():
    # Deliberately no silent rounding: dx that doesn't fit the domain is a
    # caller error to surface, not approximate quietly.
    with pytest.raises(ValueError, match="does not evenly divide"):
        cell_counts_from_dx(0.0003, (0.002, 0.002, 0.002))


def test_cell_counts_from_dx_rejects_non_positive_dx():
    with pytest.raises(ValueError, match="dx must be positive"):
        cell_counts_from_dx(0.0, (0.002, 0.002, 0.002))


def test_default_block_mesh_dict_has_a_fixed_default_cell_count_with_no_dx():
    text = default_block_mesh_dict_text()
    assert _cell_counts(text) == (4, 4, 4)


def test_dx_controls_cell_count_finer_mesh_for_smaller_dx():
    coarse = default_block_mesh_dict_text(dx_m=0.001)
    fine = default_block_mesh_dict_text(dx_m=0.0004)
    coarse_cells = _cell_counts(coarse)
    fine_cells = _cell_counts(fine)
    assert coarse_cells == (2, 2, 2)
    assert fine_cells == (5, 5, 5)
    assert fine_cells[0] > coarse_cells[0]


def test_dx_that_does_not_evenly_divide_default_slab_raises():
    with pytest.raises(ValueError, match="does not evenly divide"):
        default_block_mesh_dict_text(dx_m=0.0003)
