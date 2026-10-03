"""The generic block-mesh resolution axis.

A record instantiates it with its own ``documents``/``resolution`` to patch each ``blockMeshDict``'s ``hex (`` cell counts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

from ..case_planning import (
    hex_cell_counts_key_path, read_hex_block_extent_m, read_hex_cell_counts,
)


def _validate_documents(documents: Any) -> tuple[str, ...]:
    """Refuse a ``documents`` that is not a non-empty sequence of paths."""
    # A bare string would iterate one path per CHARACTER; refused explicitly
    # (mirrors environment._read_config_value_by_key_path).
    if isinstance(documents, str):
        raise TypeError(
            "block_mesh_resolution_axis's documents must be a sequence of "
            f"case-relative paths, not a bare string ({documents!r}) -- "
            "iterating a string yields one path per CHARACTER, which is "
            "never what a caller means"
        )
    resolved = tuple(documents)
    if not resolved:
        raise ValueError(
            "block_mesh_resolution_axis needs at least one document; got "
            "an empty sequence"
        )
    return resolved


def _validate_expected_blocks(expected_blocks: Any, *, axis_name: str) -> int:
    """Refuse an ``expected_blocks`` that is not a positive integer."""
    # bool is an int subclass in Python; True/False here is a caller
    # mistake, not a block count of 1 or 0.
    if not isinstance(expected_blocks, int) or isinstance(expected_blocks, bool):
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r}: expected_blocks must "
            f"be a positive integer, got {expected_blocks!r}"
        )
    if expected_blocks <= 0:
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r}: expected_blocks must "
            f"be a positive integer, got {expected_blocks!r}"
        )
    return expected_blocks


def _current_extents_m(
    *, staged_case_root: Path, document: str,
) -> tuple[float, float, float] | None:
    """This document's physical extent in metres, or ``None`` if unreadable."""
    document_path = Path(staged_case_root) / document
    return read_hex_block_extent_m(document_path)


def _validate_cell_counts(
    *, axis_name: str, document: str, study_value: Any, cell_counts: Any,
) -> tuple[int, int, int]:
    """Refuse unless ``cell_counts`` is exactly three positive ints."""
    # bool is an int subclass in Python; a resolution formula returning
    # True/False in a cell-count slot is a defect, not a count of 1 or 0.
    is_well_shaped = (
        isinstance(cell_counts, (tuple, list))
        and len(cell_counts) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) for c in cell_counts)
    )
    if not is_well_shaped:
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r} (document {document!r}): "
            f"resolution({study_value!r}, ...) must return a tuple of 3 "
            f"integers, got {cell_counts!r}"
        )
    non_positive = [c for c in cell_counts if c <= 0]
    if non_positive:
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r} (document {document!r}): "
            f"resolution({study_value!r}, ...) returned non-positive cell "
            f"count(s) in {cell_counts!r}; every cell count must be a "
            "positive integer"
        )
    return tuple(cell_counts)  # type: ignore[return-value]


def _current_cell_counts(
    *, axis_name: str, document: str, staged_case_root: Path, expected_blocks: int,
) -> tuple[int, int, int]:
    """The document's current hex-block cell counts; ``read_hex_cell_counts`` refuses a count mismatch by name."""
    document_path = Path(staged_case_root) / document
    if not document_path.is_file():
        raise ValueError(
            f"block-mesh-resolution axis {axis_name!r} names document "
            f"{document!r}, which does not exist in the staged case at "
            f"{staged_case_root}"
        )
    current_text = read_hex_cell_counts(document_path, expected_blocks=expected_blocks)
    assert current_text is not None  # is_file() above already confirmed existence
    return tuple(int(token) for token in current_text.split())  # type: ignore[return-value]


def block_mesh_resolution_axis(
    name: str,
    *,
    documents: Sequence[str],
    resolution: Callable[
        [Any, tuple[int, int, int], tuple[float, float, float] | None],
        tuple[int, int, int],
    ],
    expected_blocks: int = 1,
    value_kind: str = "integer",
) -> AxisContract:
    """Build a named axis mapping a study value to every named document's
    hex-block cell counts.

    ``documents`` is one or more case-relative ``blockMeshDict`` paths; one
    patch is produced per document, each carrying that document's own
    resolved counts.

    ``resolution`` is ``Callable[[value, current_counts, extents], counts]``:
    a tutorial record's own pure formula from the study value, this
    document's current cell counts, and its physical extent in metres (or
    ``None`` when the document has no parseable ``vertices``/``scale``) to
    the three new cell counts. Extents let a formula convert a physical cell
    size (e.g. Niederer's ``dx``) into cell counts without restating the
    document's own geometry as a second constant.

    ``expected_blocks`` is how many ``hex (`` blocks every named document
    must declare, all sharing one current resolution; refused by name
    otherwise at resolve time.

    ``value_kind`` declares the shape of the study value this axis's
    ``resolve`` accepts. Defaults to ``"integer"`` (a bare resolution count);
    a record whose study value is already the three cell counts passes
    ``value_kind="integer_list"`` instead.

    Refuses by name:

    - ``documents`` empty, or a bare string;
    - ``expected_blocks`` not a positive integer;
    - a named document not existing in the staged case;
    - that document's real block count disagreeing with ``expected_blocks``,
      or its blocks disagreeing with each other;
    - ``resolution(value, current_counts, extents)`` not returning exactly
      three positive integers.
    """
    resolved_documents = _validate_documents(documents)
    resolved_expected_blocks = _validate_expected_blocks(expected_blocks, axis_name=name)
    if not callable(resolution):
        raise TypeError(
            f"block-mesh-resolution axis {name!r}: resolution must be "
            f"callable, got {resolution!r}"
        )
    key_path = hex_cell_counts_key_path(expected_blocks=resolved_expected_blocks)

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        patches = []
        for document in resolved_documents:
            current_counts = _current_cell_counts(
                axis_name=name, document=document,
                staged_case_root=staged_case_root,
                expected_blocks=resolved_expected_blocks,
            )
            extents = _current_extents_m(
                staged_case_root=staged_case_root, document=document,
            )
            cell_counts = resolution(value, current_counts, extents)
            cell_counts = _validate_cell_counts(
                axis_name=name, document=document, study_value=value,
                cell_counts=cell_counts,
            )
            # `value` stays a tuple of ints (typed data, per
            # ParameterAssignment); space-joining is deferred to whichever
            # writer rewrites bytes for this key.
            #
            # value_kind is a placeholder: resolve_case_patches overwrites it
            # with the record-key validator's own answer before it reaches
            # ParameterAssignment's VALUE_KINDS check.
            patches.append(AxisPatch(
                document=document,
                key_path=key_path,
                value=cell_counts,
                value_kind="hex_cell_counts",
            ))
        return AxisResult(patches=tuple(patches))

    return AxisContract(name=name, value_kind=value_kind, resolve=resolve)
