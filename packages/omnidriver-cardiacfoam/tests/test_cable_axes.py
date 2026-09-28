"""The ``dx`` axis both cable records share (:mod:`records.cable_axes`)."""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.records.cable_axes import _dx_to_hex_cell_counts, cable_dx_axis


def test_axis_declares_a_scalar_value_kind():
    assert cable_dx_axis("dx").value_kind == "scalar"


def test_dx_resolves_the_along_cable_direction_only():
    """The cable is 0.02 m x 0.0001 m x 0.0001 m; a direction whose current count is 1 stays 1."""
    counts = _dx_to_hex_cell_counts(0.0001, current=(100, 1, 1), extents=(0.02, 0.0001, 0.0001))
    assert counts == (200, 1, 1)


def test_a_coarser_dx_gives_fewer_cells():
    counts = _dx_to_hex_cell_counts(0.001, current=(100, 1, 1), extents=(0.02, 0.0001, 0.0001))
    assert counts == (20, 1, 1)


def test_dx_that_does_not_evenly_divide_the_cable_is_refused_by_name():
    with pytest.raises(ValueError, match="does not evenly divide"):
        _dx_to_hex_cell_counts(0.0003, current=(100, 1, 1), extents=(0.02, 0.0001, 0.0001))


def test_no_extents_is_refused_by_name():
    with pytest.raises(ValueError, match="vertices/scale"):
        _dx_to_hex_cell_counts(0.0001, current=(100, 1, 1), extents=None)
