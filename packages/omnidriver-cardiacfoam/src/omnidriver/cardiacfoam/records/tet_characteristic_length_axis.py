"""The manufactured-case ``tetNumberCells`` axis (plan
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5c, 5.4b-E; evidence ``docs/solver-learning/cardiacfoam.md`` G1-G9).

A parameterised BUILDER, the same shape this package's other axis modules
use: this module knows the gmsh ``-setnumber lc <v>`` grammar the tet
``.geo.template`` route takes (``DefineConstant[ lc = {<default>, Name
"lc"} ]``, native commit ``60805b27``), not any one tutorial's own gmsh
step id -- a record instantiates this builder with its own ``gmsh_step_id``
and registers the result under whatever name it allows.

**Why ``lc = 1/N``, not a study-supplied ``lc``.** Every native
``.geo.template`` this design touches parameterises resolution by a cell
count ``N`` along the unit cube's edge (the same vocabulary
``block_mesh_resolution_axis``'s hex route uses), and G5/G8's real-gmsh
evidence confirms ``-setnumber lc <v>`` overrides the template's
``DefineConstant`` default cleanly at any value -- so this axis takes the
same ``N`` a hex study would use for ``numberCells`` and derives the one
``lc`` gmsh actually wants, rather than exposing a second, redundant "raw
characteristic length" vocabulary a study would have to get right itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import AxisContract, AxisResult


def tet_characteristic_length_axis(
    name: str,
    *,
    gmsh_step_id: str = "gmsh",
    key: tuple[str, ...] = ("-setnumber", "lc"),
) -> AxisContract:
    """Build a named axis mapping a cell count ``N`` to the ``gmsh`` step's
    ``-setnumber lc <1/N>`` argument.

    The axis declares ``value_kind="integer"`` -- checked by
    ``tutorial_records.resolve_case_patches`` before ``resolve`` ever runs,
    so a non-integer (or boolean) study value is refused by core's own
    generic shape check before reaching this module's code at all.

    Refuses by name: ``N`` not a positive integer (``bool`` excluded
    explicitly, the same reasoning ``block_mesh_resolution_axis``'s own
    ``_validate_expected_blocks``/``_validate_cell_counts`` give: a Python
    ``bool`` is an ``int`` subclass, and ``True``/``False`` here would be a
    caller mistake, not a cell count of 1 or 0).
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"tet-characteristic-length axis {name!r}: N must be a "
                f"positive integer, got {value!r}"
            )
        lc = repr(1.0 / value)
        return AxisResult(command_arguments={gmsh_step_id: key + (lc,)})

    return AxisContract(name=name, value_kind="integer", resolve=resolve)
