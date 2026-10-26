"""The blockMeshDict dx arithmetic."""

import pytest

from omnidriver.openfoam.case_planning import cell_counts_from_dx


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
