"""The manufactured-case ``dimension`` axis (plan
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5c, 5.4b-E): which ``system/blockMeshDict.<dim>`` a hex-variant case's
``mesh`` step meshes from.

A parameterised BUILDER, the same shape
``omnidriver.openfoam.axes.block_mesh_resolution_axis`` and this package's
own ``ionic_model_axis`` already use: this module knows the ``-dict
system/blockMeshDict.<dim>`` argument grammar a manufactured tutorial's
``blockMesh`` step takes, not any one tutorial's own document/scope for a
``<solver>Coeffs.dimension`` key (several manufactured cases have no such
key at all -- eikonalECG among them, see ``manufactured_eikonal_ecg.py``'s
own accounting) -- a record instantiates this builder with whichever of
those it needs and registers the result under whatever name it allows.

**Why this contributes a command argument and, optionally, a document
patch, never only the latter.** ``blockMesh`` must be told which
``blockMeshDict.<dim>`` to read; that is a ``WorkflowStep.default_arguments``
replacement (owner Q3/Q7, 2026-09-26), not a document write. A record whose
native case ALSO carries a real ``<solver>Coeffs.dimension`` key (a future
manufactured-case record) passes ``dimension_document``/``dimension_scope``
to have this axis patch that key too, in the same resolution; a record with
no such key (eikonalECG) leaves both ``None`` and gets the command
argument alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

_DEFAULT_VALUES = ("1D", "2D", "3D")


def mesh_dict_dimension_axis(
    name: str,
    *,
    mesh_step_id: str = "mesh",
    dict_key: tuple[str, ...] = ("-dict",),
    document_template: str = "system/blockMeshDict.{value}",
    values: Sequence[str] = _DEFAULT_VALUES,
    dimension_document: str | None = None,
    dimension_scope: tuple[str, ...] | None = None,
) -> AxisContract:
    """Build a named axis mapping a dimension (``"1D"``/``"2D"``/``"3D"``)
    to the ``mesh`` step's ``-dict`` argument, and, when
    ``dimension_document``/``dimension_scope`` are given, a
    ``<scope>.dimension`` patch too.

    ``values`` is the closed set of dimension names this axis accepts,
    checked in ``resolve`` itself (the axis's own declared ``value_kind``,
    ``"enum"``, checks only that the study value is a non-empty word with no
    whitespace -- membership in a specific set is this axis's own concern,
    not core's generic shape check).

    Refuses by name: a study value not in ``values``; exactly one of
    ``dimension_document``/``dimension_scope`` given without the other
    (both or neither).
    """
    resolved_values = tuple(values)
    if not resolved_values:
        raise ValueError(f"dimension axis {name!r}: values must be non-empty")
    if (dimension_document is None) != (dimension_scope is None):
        raise ValueError(
            f"dimension axis {name!r}: dimension_document and dimension_scope "
            "must be given together, or not at all"
        )

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in resolved_values:
            raise ValueError(
                f"dimension axis {name!r}: {value!r} is not one of {list(resolved_values)}"
            )
        dict_path = document_template.format(value=value)
        patches: tuple[AxisPatch, ...] = ()
        if dimension_document is not None:
            patches = (
                AxisPatch(
                    document=dimension_document,
                    key_path=dimension_scope + ("dimension",),
                    value=value,
                    value_kind="enum",
                ),
            )
        return AxisResult(
            patches=patches,
            command_arguments={mesh_step_id: dict_key + (dict_path,)},
        )

    return AxisContract(name=name, value_kind="enum", resolve=resolve)
