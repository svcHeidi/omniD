"""``polymesh`` over the ``points``, ``faces``, ``owner`` and ``neighbour`` layouts OpenFOAM v2412 writes."""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from omnidriver.openfoam.polymesh import _faces, cells_around, points_bounds

_BANNER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  2412                                  |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
"""

#: blockMesh's vertices for a unit cube (monodomain1D3D's system/blockMeshDict.3D).
_CUBE = ("(0 0 0)", "(1 0 0)", "(1 1 0)", "(0 1 0)", "(0 0 1)", "(1 0 1)", "(1 1 1)", "(0 1 1)")


def _header(layout, arch="LSB;label=32;scalar=64"):
    return (
        _BANNER + "FoamFile\n{\n    version     2.0;\n"
        f"    format      {layout};\n"
        f'    arch        "{arch}";\n    class       vectorField;\n'
        '    location    "constant/polyMesh";\n    object      points;\n}\n'
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n\n"
    )


def _points_file(tmp_path, points=_CUBE, *, layout="ascii", count=None):
    path = tmp_path / "points"
    path.write_text(
        _header(layout) + f"{len(points) if count is None else count}\n(\n" + "\n".join(points) + "\n)\n\n"
        "// ************************************************************************* //\n"
    )
    return path


def _binary_points_file(tmp_path, points=_CUBE, *, arch="LSB;label=32;scalar=64", order="<", code="d", trailer=b")\n"):
    """The layout blockMesh writes: the count, a newline, ``(``, the raw components, ``)``."""
    values = [float(component) for point in points for component in point.strip("()").split()]
    path = tmp_path / "points"
    path.write_bytes(
        _header("binary", arch).encode() + f"{len(points)}\n(".encode()
        + struct.pack(f"{order}{len(values)}{code}", *values) + trailer
    )
    return path


def test_the_corners_of_the_points_are_the_bounds(tmp_path):
    assert points_bounds(_points_file(tmp_path)) == ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


def test_negative_and_exponent_components_are_read(tmp_path):
    path = _points_file(tmp_path, ("(4.898587196e-18 0.01 0.04)", "(1.7e-18 -0.0399945136 -0.04)", "(0.07997507634 0.025 0.03)"))
    assert points_bounds(path) == ((1.7e-18, -0.0399945136, -0.04), (0.07997507634, 0.025, 0.04))


def test_an_absent_file_has_no_bounds(tmp_path):
    assert points_bounds(tmp_path / "points") is None


@pytest.mark.parametrize("arch,order,code", [
    ("LSB;label=32;scalar=64", "<", "d"),
    ("MSB;label=32;scalar=64", ">", "d"),
    ("LSB;label=32;scalar=32", "<", "f"),
])
def test_a_binary_file_is_read_in_its_own_byte_order_and_width(tmp_path, arch, order, code):
    points = ("(0.5 -2 3)", "(1.25 0.5 -4)")
    assert points_bounds(_binary_points_file(tmp_path, points, arch=arch, order=order, code=code)) == (
        (0.5, -2.0, -4.0), (1.25, 0.5, 3.0),
    )


@pytest.mark.parametrize("make,reason", [
    (lambda tmp: _points_file(tmp, layout="compressed"), "no ascii or binary list of points"),
    (lambda tmp: _points_file(tmp, count=9), "counts 9 points but holds 24 numbers"),
    (lambda tmp: _binary_points_file(tmp, trailer=b""), "counts 8 points but holds another number of bytes"),
    (lambda tmp: _binary_points_file(tmp, arch="LSB;label=32;scalar=16"), "declares no arch of 32 or 64 bit scalars"),
])
def test_a_file_that_is_not_a_counted_list_of_the_points_it_declares_is_refused(tmp_path, make, reason):
    with pytest.raises(ValueError, match=reason):
        points_bounds(make(tmp_path))


def test_an_edited_file_is_read_again(tmp_path):
    path = _points_file(tmp_path)
    assert points_bounds(path)[1] == (1.0, 1.0, 1.0)
    _points_file(tmp_path, ("(0 0 0)", "(2 0 0)"))
    assert points_bounds(path)[1] == (2.0, 0.0, 0.0)


# -------- the cells around a location --------
#
# slab_mesh is what blockMesh makes of its blockMeshDict, a 4 mm x 4 mm x 0.1 mm slab of 12 x 12 x 1 cells, in both
# layouts; cells.json holds the centres and volumes OpenFOAM v2412 computes for it (postProcess writeCellCentres
# and writeCellVolumes).

_SLAB = Path(__file__).parent / "fixtures" / "slab_mesh"
_CELL = 1e-3 / 3
_VOLUME = _CELL * _CELL * 1e-4


@pytest.mark.parametrize("layout", ["ascii", "binary"])
def test_the_distances_and_volumes_are_those_of_the_centres_and_volumes_openfoam_computes(layout):
    reference = json.loads((_SLAB / "cells.json").read_text())
    place = (1.7e-3, 2.2e-3, 0.4e-4)
    (around,) = cells_around(_SLAB / layout, [place], 5e-3)
    assert len(around.within) == 144
    for cell in around.within:
        centre = reference["centres"][cell.label]
        assert cell.volume == pytest.approx(reference["volumes"][cell.label], rel=1e-5)
        assert cell.distance == pytest.approx(sum((a - b) ** 2 for a, b in zip(place, centre)) ** 0.5, abs=1e-8)


def test_a_junction_on_a_cell_corner_has_the_four_cells_around_it_and_the_eight_beyond():
    corner = (2e-3, 2e-3, 0.5e-4)
    (wide,) = cells_around(_SLAB / "ascii", [corner], 0.6e-3)
    assert len(wide.within) == 12
    assert sorted(cell.distance for cell in wide.within)[:4] == pytest.approx([_CELL / 2 ** 0.5] * 4)
    assert all(cell.volume == pytest.approx(_VOLUME) for cell in wide.within)
    (narrow,) = cells_around(_SLAB / "ascii", [corner], 0.5e-3)
    assert len(narrow.within) == 4


def test_the_nearest_cell_is_returned_when_none_is_within_the_radius():
    (outside,) = cells_around(_SLAB / "ascii", [(5e-3, 6.5 * _CELL, 0.5e-4)], 0.5e-3)
    assert outside.within == [] and outside.nearest.distance == pytest.approx(5e-3 - (4e-3 - _CELL / 2))


def test_a_location_far_from_every_cell_examines_none():
    (far,) = cells_around(_SLAB / "ascii", [(1.0, 0.0, 0.0)], 0.5e-3)
    assert far.within == [] and far.nearest is None


def test_only_the_cells_near_a_location_are_read_as_cells():
    """The corner of the slab: its geometry is the same whether other locations are asked for or not."""
    near, far = (0.1e-3, 0.1e-3, 0.5e-4), (3.9e-3, 3.9e-3, 0.5e-4)
    (alone,) = cells_around(_SLAB / "ascii", [near], 0.5e-3)
    both = cells_around(_SLAB / "ascii", [near, far], 0.5e-3)
    assert both[0] == alone and len(both[1].within) == 3


def _copy_mesh(tmp_path, layout="ascii"):
    for name in ("points", "faces", "owner", "neighbour"):
        shutil.copy(_SLAB / layout / name, tmp_path / name)
    return tmp_path


def test_a_compressed_mesh_says_it_cannot_be_read(tmp_path):
    mesh = _copy_mesh(tmp_path)
    (mesh / "faces").rename(mesh / "faces.gz")
    with pytest.raises(ValueError, match="faces.gz is compressed"):
        cells_around(mesh, [(0.0, 0.0, 0.0)], 1e-3)
    (mesh / "points").rename(mesh / "points.gz")
    with pytest.raises(ValueError, match="points.gz is compressed"):
        points_bounds(mesh / "points")


def test_an_absent_mesh_is_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        cells_around(tmp_path, [(0.0, 0.0, 0.0)], 1e-3)


def test_a_face_of_more_than_ten_points_is_read_across_its_lines(tmp_path):
    """polyDualMesh's faces: OpenFOAM writes a list of more than ten entries as ``11\\n(\\n...\\n)``."""
    mesh = tmp_path / "polyMesh"
    mesh.mkdir()
    shutil.copy(_SLAB / "faces_split_across_lines", mesh / "faces")
    labels, offsets = _faces(mesh)
    assert [offsets[i + 1] - offsets[i] for i in range(len(offsets) - 1)] == [5, 8, 11, 7, 5]
    assert list(labels[offsets[2]:offsets[3]])[:3] == [138528, 143216, 149113]


def test_a_face_counted_wrongly_is_refused(tmp_path):
    mesh = tmp_path / "polyMesh"
    mesh.mkdir()
    text = (_SLAB / "faces_split_across_lines").read_text().replace("5(138528 143178 138771 141093 140524)", "6(138528 143178 138771 141093 140524)")
    (mesh / "faces").write_text(text)
    with pytest.raises(ValueError, match="a face of 5 points counted as 6"):
        _faces(mesh)


def test_the_class_is_the_headers_not_a_word_in_it(tmp_path):
    mesh = _copy_mesh(tmp_path)
    (mesh / "faces").write_text((mesh / "faces").read_text().replace("object      faces;", 'object      faces;\n    note        "faceCompactList";'))
    (around,) = cells_around(mesh, [(2e-3, 2e-3, 0.5e-4)], 0.6e-3)
    assert len(around.within) == 12


def test_a_mesh_with_too_many_cells_near_the_locations_is_refused_not_read_for_minutes(monkeypatch):
    monkeypatch.setattr("omnidriver.openfoam.polymesh.FACE_LIMIT", 20)
    with pytest.raises(ValueError, match="more than the 20 omniD reads"):
        cells_around(_SLAB / "ascii", [(2e-3, 2e-3, 0.5e-4)], 0.6e-3)
