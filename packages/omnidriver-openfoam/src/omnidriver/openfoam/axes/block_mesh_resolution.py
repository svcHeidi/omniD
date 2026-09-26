"""The OpenFOAM package's one generic axis (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §3,
"OpenFOAM package: generic axes", corrected 2026-09-25 by the owner to name
only this axis -- gmsh's ``lc`` and the dt unit conversion are not OpenFOAM's
to own; see that section's dated correction).

``block_mesh_resolution_axis`` is a PARAMETERISED BUILDER, not a fixed-name
axis: this package knows OpenFOAM (a ``blockMeshDict``'s ``hex (`` grammar),
not any tutorial's own choice of document or resolution formula, so a
tutorial record (a cardiac record, step 4/5) instantiates this builder with
its own ``documents``/``resolution`` and registers the result under whatever
name it chooses -- nothing here is registered into any plugin's catalog
(YAGNI: nothing needs a fixed-name instance yet).

**Corrected 2026-09-25** (``restitutionCurves``'s ``blockMeshResolution``
axis, a genuine study choice the tutorial's own ``system/blockMeshDict``
documents as three commented-out alternatives): the builder's ``value_kind``
was hardcoded to ``"integer"``, which fit only the "one count, expanded by a
formula" case this module's docstring already described. It is now a
parameter (default unchanged, ``"integer"``) so a record whose study value
is already the three cell counts can declare ``value_kind="integer_list"``
instead -- see :func:`block_mesh_resolution_axis`'s own docstring.

**Corrected 2026-09-26 (P2,
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5e).** This used to take a single ``document`` and a ``resolution`` that
saw only the study value -- fine for ``restitutionCurves``'s one-document,
one-block case, but bathBidomain needs the same one study value (``N``)
applied to its THREE ``blockMeshDict.<dim>`` documents at once, each with
its own current resolution and its own count of directions actually
refined (owner decision (d), design doc's step 4a: "a direction whose
current count is 1 stays 1... reading which directions are refined FROM
EACH FILE ITSELF"). Three changes, all owner-decided (P2's own three
bullets):

- ``document`` (one path) became ``documents`` (one or more), so a single
  axis instance patches every ``blockMeshDict.<dim>`` a tutorial has, not
  one dimension's file alone.
- ``expected_blocks`` is now a required, per-axis-instance argument (a
  record states it, e.g. bath's ``3``) rather than each document's writer
  and reader defaulting it to 1 independently of what the record actually
  declares -- see :func:`omnidriver.openfoam.case_planning
  .hex_cell_counts_key_path` for how this axis threads that count through
  the produced patch instead.
- ``resolution`` now takes the STUDY VALUE *and* that document's own
  current cell counts (read by this axis, once per document, via
  :func:`.case_planning.read_hex_cell_counts`): ``Callable[[value,
  current_counts], counts]``. This is what makes "a direction whose current
  count is 1 stays 1" a REUSABLE resolution a record can write once and
  pass here, rather than this package inventing per-dimension knowledge of
  which axes a given tutorial refines (design's own words: "there is no
  per-dimension table naming which axes a given tutorial refines, which
  would restate what each ``blockMeshDict.<dim>`` already says").

One direct consequence: this axis now reads each document's actual
``hex (`` content (via ``read_hex_cell_counts``) to hand ``resolution`` the
current counts it needs -- it is no longer a plain existence check. That
read already performs the SAME ``expected_blocks`` check
``plan_block_mesh_resolution``'s docstring used to describe as "deferred to
the renderer" (see this module's OLD docstring, superseded by this
correction): a document whose real block count disagrees with what the
record declared is refused HERE, at ``resolve()`` time, not only when a
future writer eventually renders the patch. See the pinning test's own
2026-09-26 correction (``test_axes_block_mesh_resolution.py``) for exactly
what changed and why.

**Why the produced patch is not a ``document:key`` edit.**
:func:`omnidriver.openfoam.case_planning.plan_block_mesh_resolution`'s own
docstring already gives the full reasoning: rewriting every ``hex (`` block
declaration in an existing document is not a key/value set (there is no
single ``key_path`` a caller could name, and how many blocks were actually
rewritten is itself part of what is asserted, not a value being assigned).
This axis carries that same target forward as one
:class:`~omnidriver.core.tutorial_records.AxisPatch` addressed at
:func:`.case_planning.hex_cell_counts_key_path`'s own synthetic key path --
which now also carries this axis instance's ``expected_blocks`` (P2, above),
so the writer and the reader that later act on this patch need not
independently guess it. ``value_kind="hex_cell_counts"`` is not one of
core's own declared ``VALUE_KINDS`` (``case_write.VALUE_KINDS``) and is
never checked against them here: ``tutorial_records.resolve_case_patches``
overwrites an axis-produced patch's ``value_kind`` with whatever the
composed stack's own record-key validator answers for this
``(document, key_path, value)`` before it ever reaches
``patches_to_parameters``/``ParameterAssignment`` (whose ``value_kind`` field
*is* checked against ``VALUE_KINDS``) -- this placeholder is purely
descriptive and is discarded well before that point.

**Corrected 2026-09-25 (the ``restitutionCurves`` real-run test's own
regression).** The patch's ``value`` used to be the pre-formatted,
space-joined TEXT (``plan_block_mesh_resolution``'s own
``"hex_cell_counts"`` string, e.g. ``"40 6 14"``), built by calling that
planner right here in ``resolve()``. That is rendered text carried as data
-- exactly what ``case_write.py``'s own 2026-09-23 decision says a
``ParameterAssignment`` must never be ("a value is native Python data,
checked against its declared shape here, not rendered text checked
nowhere"), and no ``VALUE_KINDS`` member fits an arbitrary string
containing whitespace (``word``/``enum`` both refuse it by name). This
axis had no production caller until the ``restitutionCurves`` pilot's real
run, so the mismatch was never exercised: every prior use only previewed a
patch or asserted it "unchanged" (``split_unchanged`` never reaches
``patches_to_parameters``), and neither path ever ran ``value_kind``
through ``validate_value_shape``. ``resolve()`` now returns the validated
TUPLE of ints as ``value`` -- a real ``integer_list`` shape, checked
successfully -- and defers space-joining (and ``plan_block_mesh_resolution``'s
own security check) to whichever writer actually rewrites bytes for this
key (``cardiacfoam.overrides._target_for_parameter``, which reuses
``plan_block_mesh_resolution`` itself, same as this axis used to).

**Corrected 2026-09-25 (later the same day, review B-I7).** "No
``VALUE_KINDS`` member fits an arbitrary string containing whitespace" stopped
being true when core gained ``string`` (K6) for openCARP's text-typed
parameters. The conclusion stands for a different reason: ``"40 6 14"`` is
three integers rendered as text, and ``string`` is only for values whose
native type is text (see the note under ``contracts.dictionary.VALUE_KINDS``),
so ``integer_list`` remains the right shape and ``string`` must not carry it.

**What the axis DOES check itself** (refusing by name):

- at build time (``block_mesh_resolution_axis(...)`` itself, before any
  study ever resolves): ``documents`` is a non-empty sequence of case-relative
  paths, never a bare string (the same "a string iterates one path per
  CHARACTER" mistake ``environment._read_config_value_by_key_path`` already
  refuses); ``expected_blocks`` is a positive integer; ``resolution`` is
  callable;
- at resolve time, per document: the document exists in the staged case,
  and its real ``hex (`` block count matches ``expected_blocks`` (via
  ``read_hex_cell_counts``, which also refuses disagreeing blocks -- see its
  own 2026-09-26 correction); ``resolution(value, current_counts)`` must
  return exactly three positive integers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

from ..case_planning import hex_cell_counts_key_path, read_hex_cell_counts


def _validate_documents(documents: Any) -> tuple[str, ...]:
    """Refuse by name a ``documents`` argument that is not a non-empty
    sequence of case-relative path strings.

    A bare string is refused explicitly (mirrors
    ``environment._read_config_value_by_key_path``'s own refusal): a caller
    passing ``document="system/blockMeshDict"`` where the builder now wants
    ``documents=(...)`` would otherwise have that single string iterated
    character-by-character, silently trying to patch a document per letter.
    """
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
    """Refuse by name an ``expected_blocks`` that is not a positive integer.

    ``bool`` excluded explicitly, the same reasoning
    ``_validate_cell_counts`` already gives for a resolution's own output:
    ``bool`` is an ``int`` subclass in Python, and ``True``/``False`` here
    would be a caller mistake, not a block count of 1 or 0.
    """
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
    """This document's current hex-block cell counts, as a tuple of ints --
    what ``resolution`` needs to know to keep a direction at 1 (decision (d)).

    Refuses by name when the document does not exist in the staged case.
    ``read_hex_cell_counts`` itself refuses by name (``KeyError``) when the
    document's real block count does not equal ``expected_blocks``, or when
    ``expected_blocks`` real blocks disagree on their counts -- both reused
    here, not re-implemented.
    """
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
    resolution: Callable[[Any, tuple[int, int, int]], tuple[int, int, int]],
    expected_blocks: int = 1,
    value_kind: str = "integer",
) -> AxisContract:
    """Build a named axis mapping a study value to every named document's
    hex-block cell counts.

    ``documents`` is one or more case-relative ``blockMeshDict`` paths (e.g.
    ``("system/blockMeshDict.1D", "system/blockMeshDict.2D",
    "system/blockMeshDict.3D")`` for bathBidomain, or a single-element
    sequence for a tutorial with only one such document). One patch is
    produced per document, each carrying that document's own resolved
    counts -- this axis never assumes every document resolves to the same
    triple.

    ``resolution`` is a pure callable from the study value AND this
    document's own current cell counts to the three new cell counts --
    ``Callable[[value, current_counts], counts]``. A tutorial record's own
    formula, e.g. ``lambda n, current: (n, n, n)`` for an isotropic
    resolution that ignores the document's current state entirely, or a
    formula that keeps a direction at its current count when that count is
    1 (owner decision (d): "a direction whose current count is 1 stays 1"),
    e.g. ``lambda n, current: tuple(n if c != 1 else 1 for c in current)`` --
    this package knows neither the formula nor which documents any
    particular tutorial uses, only how to read a document's current state
    and turn "some cell counts" into a patch once it has them.

    ``expected_blocks`` (added 2026-09-26, P2) is how many ``hex (`` blocks
    EVERY named document declares -- stated by the record (e.g. bath's
    ``3``), not independently defaulted by a downstream writer or reader.
    Every document this axis names must have exactly this many real
    ``hex (`` blocks, all sharing one current resolution (see
    ``read_hex_cell_counts``'s own 2026-09-26 correction) -- refused by name
    otherwise, at resolve time, for every document this axis touches. One
    resolved triple is then written to every block in a given document.

    ``value_kind`` declares the shape of the STUDY value this axis's
    ``resolve`` accepts -- checked by ``tutorial_records.resolve_case_patches``
    before ``resolution`` ever runs, so a value not fitting that shape is
    refused by core's own generic shape check before reaching this module's
    code at all. Defaults to ``"integer"`` (the design's original concrete
    vocabulary for this axis: a bare resolution count, e.g.
    ``number_cells: 20``). A record whose study value is the three cell
    counts themselves (not a single count a formula expands) passes
    ``value_kind="integer_list"`` instead -- the closest existing
    ``contracts.dictionary.VALUE_KINDS`` member for "a list of three ints"
    (no fixed-length-3 kind exists; this axis's own ``_validate_cell_counts``
    already enforces the exact length and positivity `resolution` must
    return, so ``integer_list``'s per-element-only check is sufficient here,
    not a gap).

    Refuses by name (module docstring has the full reasoning for each):

    - ``documents`` empty, or a bare string;
    - ``expected_blocks`` not a positive integer;
    - a named document not existing in the staged case;
    - that document's real block count disagreeing with ``expected_blocks``,
      or its blocks disagreeing with each other (``read_hex_cell_counts``);
    - ``resolution(value, current_counts)`` not returning exactly three
      positive integers, for any named document.
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
            cell_counts = resolution(value, current_counts)
            cell_counts = _validate_cell_counts(
                axis_name=name, document=document, study_value=value,
                cell_counts=cell_counts,
            )
            # `value` is the validated TUPLE of ints (2026-09-25 correction):
            # typed data, matching `ParameterAssignment`'s own "never
            # rendered text" rule, and a real `integer_list` shape
            # `validate_value_shape` actually accepts. Space-joining into
            # `plan_block_mesh_resolution`'s own `"hex_cell_counts"` string
            # (and its security check) is deferred to whichever writer
            # actually rewrites bytes for this key.
            patches.append(AxisPatch(
                document=document,
                key_path=key_path,
                value=cell_counts,
                value_kind="hex_cell_counts",
            ))
        return AxisResult(patches=tuple(patches))

    return AxisContract(name=name, value_kind=value_kind, resolve=resolve)
