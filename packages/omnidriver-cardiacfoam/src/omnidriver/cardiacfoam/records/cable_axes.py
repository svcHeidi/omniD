"""The axis ``cable1DRestitution`` and ``cable1DCVConvergence`` share (both
point at ``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV``,
tutorials-are-pointers plan §5e "5.2/5.3 ... same native case
``cableProtocol``").

The case's own ``system/blockMeshDict`` is a single ``hex (`` block
``(100 1 1)`` over a 20 mm x 0.1 mm x 0.1 mm cable (scale ``0.001``): only
the along-cable direction is ever refined, the cross-section stays a single
cell at every resolution a committed study uses. Real runs (logged in
``docs/solver-learning/cardiacfoam.md`` under "cable"): a ``dx`` of 0.1 mm
against this cable gives ``(200 1 1)``, matching the old module's own
``cell_counts_from_dx(dx_mm, (cable_length_mm,))`` call, minus the Python
constant -- this reads the cable's length from the document itself
(``block_mesh_resolution_axis``'s ``extents``), never restating it.
"""

from __future__ import annotations

from typing import Any

from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.mesh_provisioning import cell_counts_from_dx

BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"


def _dx_to_hex_cell_counts(
    dx_m: Any, current: tuple[int, int, int],
    extents: tuple[float, float, float] | None,
) -> tuple[int, int, int]:
    """Owner decision (d): a direction whose CURRENT cell count is 1 stays
    1; every other direction is resolved from ``dx`` (metres) against that
    direction's own physical extent (:func:`cell_counts_from_dx`), read live
    from ``system/blockMeshDict`` itself, never a Python constant.
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
