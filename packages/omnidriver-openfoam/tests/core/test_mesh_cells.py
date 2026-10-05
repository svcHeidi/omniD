"""``mesh_cells.cell_geometry`` against the centres and volumes OpenFOAM v2412 computes for the mesh its ``blockMesh``
makes of ``fixtures/slab_mesh/blockMeshDict``, in both the ascii and the binary layout."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from omnidriver.openfoam.mesh_cells import cell_geometry

_SLAB = Path(__file__).parent / "fixtures" / "slab_mesh"
_CELL = 1e-3 / 3  # 4 mm over 12 cells


@pytest.fixture(scope="module")
def reference():
    return json.loads((_SLAB / "cells.json").read_text())


@pytest.mark.parametrize("layout", ["ascii", "binary"])
def test_the_centres_and_volumes_are_those_openfoam_computes(layout, reference):
    geometry = cell_geometry(_SLAB / layout)
    assert len(geometry.volume) == len(reference["volumes"]) == 144
    for cell, (volume, centre) in enumerate(zip(reference["volumes"], reference["centres"])):
        assert geometry.volume[cell] == pytest.approx(volume, rel=1e-5)
        assert (geometry.x[cell], geometry.y[cell], geometry.z[cell]) == pytest.approx(centre, abs=1e-8)


def test_the_cells_near_a_point_are_those_within_the_radius():
    """A junction on a cell corner at the middle of the slab: its four cells, then the eight beyond them."""
    geometry = cell_geometry(_SLAB / "ascii")
    corner = (2e-3, 2e-3, 0.5e-4)
    around = geometry.near(corner, 0.6e-3)
    assert len(around) == 12
    assert sorted(d for d, _ in around)[:4] == pytest.approx([_CELL / 2 ** 0.5] * 4)
    assert all(volume == pytest.approx(_CELL * _CELL * 1e-4) for _, volume in around)
    assert len(geometry.near(corner, 0.5e-3)) == 4


def test_the_nearest_cell_of_a_point_outside_the_mesh_is_found_or_not():
    geometry = cell_geometry(_SLAB / "ascii")
    beside_a_row = (5e-3, 6.5 * _CELL, 0.5e-4)
    distance, volume = geometry.nearest(beside_a_row, 0.5e-3)
    assert distance == pytest.approx(5e-3 - (4e-3 - _CELL / 2)) and volume == pytest.approx(_CELL * _CELL * 1e-4)
    assert geometry.nearest((1.0, 0.0, 0.0), 0.5e-3, limit=5) is None


def test_files_that_are_no_mesh_are_refused(tmp_path):
    for name in ("points", "faces", "owner", "neighbour"):
        shutil.copy(_SLAB / "ascii" / name, tmp_path / name)
    (tmp_path / "owner").write_text(
        (tmp_path / "owner").read_text().replace("format      ascii;", "format      compressed;")
    )
    with pytest.raises(ValueError, match="no ascii or binary list"):
        cell_geometry(tmp_path)
