"""Generic default `system/blockMeshDict` for a case with no author-supplied
geometry: a small slab, not tuned to any tutorial's science. Which solver
wants this vs. a fixed one-cell resolution is a plugin decision.
"""

from __future__ import annotations

from collections.abc import Sequence

_DEFAULT_BLOCK_MESH_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v1912                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// Generic default geometry for a from-scratch case_folder with no
// author-supplied blockMeshDict. Not tuned to any specific tutorial's
// science -- author your own blockMeshDict if geometry matters.

scale   0.001;

vertices
(
    (0 0 0)
    (2 0 0)
    (2 2 0)
    (0 2 0)
    (0 0 2)
    (2 0 2)
    (2 2 2)
    (0 2 2)
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (__CELLS__ __CELLS__ __CELLS__) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    walls
    {
        type patch;
        faces
        (
            (3 7 6 2)
            (0 4 7 3)
            (2 6 5 1)
            (1 5 4 0)
            (0 3 2 1)
            (4 5 6 7)
        );
    }
);

mergePatchPairs
(
);

// ************************************************************************* //
"""


# Matches `scale 0.001` and the 0..2 vertex extent in
# _DEFAULT_BLOCK_MESH_DICT above (2 * 0.001 = 0.002 m).
_DEFAULT_SLAB_SIZE_M: tuple[float, float, float] = (0.002, 0.002, 0.002)
_DEFAULT_CELLS = 4


def cell_counts_from_dx(dx: float, slab_size: Sequence[float]) -> tuple[int, ...]:
    """Integer cell count per axis for isotropic cell size `dx` over
    `slab_size`'s axis lengths (same unit for both; no conversion).

    Raises `ValueError` if `dx` does not evenly divide an axis length,
    deliberately, rather than rounding.
    """
    if dx <= 0:
        raise ValueError(f"dx must be positive; got {dx}")
    counts: list[int] = []
    for axis_length in slab_size:
        raw_cells = float(axis_length) / dx
        rounded_cells = round(raw_cells)
        if abs(raw_cells - rounded_cells) > 1e-9:
            raise ValueError(
                f"dx={dx} does not evenly divide slab axis length {axis_length}"
            )
        if rounded_cells <= 0:
            raise ValueError(
                f"Computed non-positive cell count for axis length {axis_length} with dx={dx}"
            )
        counts.append(int(rounded_cells))
    return tuple(counts)


def default_block_mesh_dict_text(*, dx_m: float | None = None) -> str:
    """Generic default `system/blockMeshDict` text (a small slab, "walls" patch).

    `dx_m` derives the cell count via `cell_counts_from_dx`; omit for the
    fixed default cell count.
    """
    if dx_m is None:
        cells = _DEFAULT_CELLS
    else:
        counts = cell_counts_from_dx(dx_m, _DEFAULT_SLAB_SIZE_M)
        cells = counts[0]
    return _DEFAULT_BLOCK_MESH_DICT.replace("__CELLS__", str(cells))


def single_cell_block_mesh_dict_text() -> str:
    """`system/blockMeshDict` for a solver with no real spatial geometry: the
    generic slab resolved to exactly one hex cell, matching the native
    `singleCell` tutorial.

    electroModel.C requires a real `fvMesh` regardless of solver, so even a
    single-cell solver goes through the same blockMeshDict/blockMesh path.
    """
    return default_block_mesh_dict_text(dx_m=_DEFAULT_SLAB_SIZE_M[0])
