"""The ``dx`` axis ``cable1DRestitution`` and ``cable1DCVConvergence`` share,
both pointing at ``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV``.
See ``docs/solver-learning/cardiacfoam.md`` section CABLE for real-run evidence.
"""

from __future__ import annotations

from typing import Any

from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.case_planning import cell_counts_from_dx

BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"


def _dx_to_hex_cell_counts(
    dx_m: Any, current: tuple[int, int, int],
    extents: tuple[float, float, float] | None,
) -> tuple[int, int, int]:
    """A direction whose current cell count is 1 stays 1; every other direction
    is resolved from ``dx`` (metres) against that direction's own physical
    extent, read live from ``system/blockMeshDict``, never a Python constant.
    """
    if extents is None:
        raise ValueError(
            f"{BLOCK_MESH_DICT_DOCUMENT!r} has no parseable vertices/scale "
            "to read a physical extent from"
        )
    dx = float(dx_m)
    return tuple(
        cell_counts_from_dx(dx, (extents[i],))[0] if current[i] != 1 else 1
        for i in range(3)
    )


def cable_dx_axis(name: str):
    """A named ``dx`` axis (metres) over the cable's own
    ``system/blockMeshDict``, shared by both cable tutorials."""
    return block_mesh_resolution_axis(
        name, documents=(BLOCK_MESH_DICT_DOCUMENT,),
        resolution=_dx_to_hex_cell_counts, expected_blocks=1, value_kind="scalar",
    )
