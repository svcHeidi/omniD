"""``mesh_points.points_bounds`` over the ``points`` file layout OpenFOAM v2412 writes."""

from __future__ import annotations

import struct

import pytest

from omnidriver.openfoam.mesh_points import points_bounds

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
