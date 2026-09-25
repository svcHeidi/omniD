"""The OpenFOAM package's one generic axis (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §3,
"OpenFOAM package: generic axes", corrected 2026-09-25 by the owner to name
only this axis -- gmsh's ``lc`` and the dt unit conversion are not OpenFOAM's
to own; see that section's dated correction).

``block_mesh_resolution_axis`` is a PARAMETERISED BUILDER, not a fixed-name
axis: this package knows OpenFOAM (a ``blockMeshDict``'s ``hex (`` grammar),
not any tutorial's own choice of document or resolution formula, so a
tutorial record (a cardiac record, step 4/5) instantiates this builder with
its own ``document``/``resolution`` and registers the result under whatever
name it chooses -- nothing here is registered into any plugin's catalog
(YAGNI: nothing needs a fixed-name instance yet).

**Why the produced patch is not a ``document:key`` edit.**
:func:`omnidriver.openfoam.case_planning.plan_block_mesh_resolution`'s own
docstring already gives the full reasoning: rewriting every ``hex (`` block
declaration in an existing document is not a key/value set (there is no
single ``key_path`` a caller could name, and how many blocks were actually
rewritten is itself part of what is asserted, not a value being assigned).
This axis carries that same target forward as one
:class:`~omnidriver.core.tutorial_records.AxisPatch` addressed at the
synthetic key path ``("hex_cell_counts",)`` -- the same field name
``plan_block_mesh_resolution`` already uses for it -- rather than inventing a
second representation. ``value_kind="hex_cell_counts"`` is not one of core's
own declared ``VALUE_KINDS`` (``case_write.VALUE_KINDS``) and is never
checked against them here: ``tutorial_records.resolve_case_patches``
overwrites an axis-produced patch's ``value_kind`` with whatever the
composed stack's own record-key validator answers for this
``(document, key_path, value)`` before it ever reaches
``patches_to_parameters``/``ParameterAssignment`` (whose ``value_kind`` field
*is* checked against ``VALUE_KINDS``) -- this placeholder is purely
descriptive and is discarded well before that point.

**Why "exactly one hex block" is not checked here.**
``plan_block_mesh_resolution`` itself performs no such check either -- by its
own docstring, it "does **not** check ``expected_blocks`` against a real
file... That check is the renderer's job"
(:func:`omnidriver.openfoam.case_rendering.render_patch_case_files`, via
:func:`omnidriver.openfoam.case_planning._rewrite_hex_block_lines`). This
axis calls ``plan_block_mesh_resolution`` with its default
``expected_blocks=1`` and carries that value forward inside the patch's
target shape; whichever future writer commits a ``"hex_cell_counts"`` patch
for real reuses that same already-tested check (not duplicated here) the
moment it actually rewrites bytes. Proven necessary, not merely convenient:
the real ``manufacturedSolutions/bathBidomain/system/blockMeshDict.3D`` (see
this package's native tests) has THREE ``hex (`` blocks, not one, and a
resolution axis targeting it must still be able to compute and report a
patch value for it (e.g. for `describe`'s preview, or for the "unchanged"
check) -- an eager read-and-count refusal at axis-resolve time would refuse
that real, legitimate case before any renderer specific to bathBidomain's own
``expected_blocks=3`` call ever ran.

**What the axis DOES check itself** (refusing by name, before any read):
``resolution(value)`` must return exactly three positive integers -- a
non-integer or non-positive count is a caller (record-authoring) mistake,
not something any existing planner already refuses, so it is refused here,
once. The one file read this axis performs is a plain existence check
(`Path.is_file()`) against the staged case -- "the axis reads nothing it
does not need": it does not open or parse the document's bytes at all, only
confirms it is there before proposing an edit to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

from ..case_planning import plan_block_mesh_resolution

#: The synthetic key path every patch this axis produces carries -- not a
#: literal ``blockMeshDict`` dictionary key (there is none for "every hex
#: block's cell counts"), but the same field name
#: ``plan_block_mesh_resolution``'s own target dict already uses for this
#: edit, reused rather than re-named.
_HEX_CELL_COUNTS_KEY_PATH = ("hex_cell_counts",)


def _validate_cell_counts(
    *, axis_name: str, document: str, study_value: Any, cell_counts: Any,
) -> tuple[int, int, int]:
    """Refuse by name unless ``cell_counts`` is exactly three positive ints.

    ``bool`` is a ``int`` subclass in Python, so it is excluded explicitly --
    a resolution formula returning ``True``/``False`` in a cell-count slot is
    a defect, not a count of 1 or 0.
    """
    is_well_shaped = (
        isinstance(cell_counts, (tuple, list))
        and len(cell_counts) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) for c in cell_counts)
    )
    if not is_well_shaped:
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r} (document {document!r}): "
            f"resolution({study_value!r}) must return a tuple of 3 integers, "
            f"got {cell_counts!r}"
        )
    non_positive = [c for c in cell_counts if c <= 0]
    if non_positive:
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r} (document {document!r}): "
            f"resolution({study_value!r}) returned non-positive cell count(s) "
            f"in {cell_counts!r}; every cell count must be a positive integer"
        )
    return tuple(cell_counts)  # type: ignore[return-value]


def block_mesh_resolution_axis(
    name: str,
    *,
    document: str,
    resolution: Callable[[Any], tuple[int, int, int]],
) -> AxisContract:
    """Build a named axis mapping a study value to a ``blockMeshDict``'s hex
    block cell counts.

    ``document`` is the case-relative ``blockMeshDict`` path (e.g.
    ``"system/blockMeshDict.3D"``). ``resolution`` is a pure callable from
    the study value to the three cell counts -- a tutorial record's own
    formula (e.g. ``lambda n: (n, n, n)`` for an isotropic resolution, or a
    per-dimension one); this package knows neither the formula nor which
    document any particular tutorial uses, only how to turn "some cell
    counts" into a patch once it has them.

    The axis declares ``value_kind="integer"`` for the STUDY value it
    accepts (the one concrete study vocabulary the design names for this
    axis is a bare resolution count, e.g. ``number_cells: 20``) -- checked by
    ``tutorial_records.resolve_case_patches`` before ``resolution`` ever
    runs, so a non-integer study value (a string, a float) is refused by
    core's own generic shape check before reaching this module's code at
    all.

    Refuses by name (module docstring has the full reasoning for each):

    - ``resolution(value)`` not returning exactly three positive integers;
    - ``document`` not existing in the staged case (an existence check only
      -- this axis never reads the document's content).
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        cell_counts = resolution(value)
        cell_counts = _validate_cell_counts(
            axis_name=name, document=document, study_value=value, cell_counts=cell_counts,
        )
        document_path = Path(staged_case_root) / document
        if not document_path.is_file():
            raise ValueError(
                f"block-mesh-resolution axis {name!r} names document "
                f"{document!r}, which does not exist in the staged case at "
                f"{staged_case_root}"
            )
        cell_counts_str = " ".join(str(count) for count in cell_counts)
        # Reused, not duplicated: `plan_block_mesh_resolution` both formats
        # (and security-checks, via `literals._format_value`) the cell-count
        # string and shapes the target `render_patch_case_files` understands
        # -- `expected_blocks` stays at its default (1); see module docstring
        # for why checking it against this document's real content is not
        # this axis's job.
        target = plan_block_mesh_resolution(document, cell_counts_str)
        patch = AxisPatch(
            document=target["document"],
            key_path=_HEX_CELL_COUNTS_KEY_PATH,
            value=target["hex_cell_counts"],
            value_kind="hex_cell_counts",
        )
        return AxisResult(patches=(patch,))

    return AxisContract(name=name, value_kind="integer", resolve=resolve)
