"""Pure OpenFOAM case-edit planners -- no writer lives here (review finding
M2, the ``utils.py`` split).

Every function in this module reads nothing and writes nothing: each
resolves a requested edit into a raw ``render_patch_case_files`` target
mapping for the render/commit channel to act on later. The planners used to
share ``utils.py`` with their writer counterparts (``set_delta_t`` and kin),
which made it impossible for a tutorial-record axis to import a pure
planner without ALSO being able to reach a writer one import away. An axis
module (``openfoam/axes/``) may import from here;
``scripts/check-case-writes.py`` scans this module and bans importing
``omnidriver.openfoam.utils``.

Corrected 2026-09-26 (review 54b M6): ``utils.py`` is deleted. Its last
writer, ``set_delta_t``, was retired with the niederer2011 migration, and
it was kept empty "since a future direct writer may still need to land
here"; nothing imported it. The gate still bans the name, so a writer
module re-created there stays unreachable from an axis.

Corrected 2026-09-27 (tutorials-are-pointers step C): ``plan_delta_t``/
``plan_end_time``, the two planners here that produced a real
``ParameterAssignment`` rather than a raw target mapping, are deleted --
their only production caller was cardiacFoam's factory-tutorial path
(``manufactured_monodomain_total_lagrangian_em.py``), deleted the same day.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Mapping

from .literals import _format_value

#: The synthetic key path a ``blockMeshDict``'s hex-block cell counts are
#: addressed at -- design's own words: "there is no single ``key_path`` a
#: caller could name" for rewriting every ``hex (`` line, so this stands in
#: for one (see :func:`plan_block_mesh_resolution`'s docstring). Owned here,
#: beside the planner that defines the ``"hex_cell_counts"`` field name
#: itself, so :mod:`.axes.block_mesh_resolution` (the axis that produces a
#: patch at this key path) and :func:`read_hex_cell_counts`/
#: :func:`.environment._read_config_value_by_key_path` (the reader that
#: answers "what is it now") share ONE spelling of the convention rather than
#: three independently-typed copies of the literal ``("hex_cell_counts",)``.
#:
#: **This is the BARE, one-block spelling** -- a direct
#: ``document:hex_cell_counts`` study key (no axis at all;
#: ``test_record_key_validation_native.py``'s own real-cardiac-stack check
#: uses exactly this) sorts to this literal tuple, and it always means
#: ``expected_blocks=1``, the same default :func:`read_hex_cell_counts`/
#: :func:`plan_block_mesh_resolution` already had. See
#: :func:`hex_cell_counts_key_path` for the multi-block spelling
#: (P2, 2026-09-26): a document declaring more than one block gets a second
#: segment naming the count, so the actual count a record declares travels
#: with the patch instead of every reader/writer independently assuming 1.
HEX_CELL_COUNTS_KEY_PATH: tuple[str, ...] = ("hex_cell_counts",)


def hex_cell_counts_key_path(*, expected_blocks: int) -> tuple[str, ...]:
    """The key path a hex-cell-counts patch is addressed at, carrying
    ``expected_blocks`` through the patch itself (P2, 2026-09-26,
    ``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
    §5e) rather than letting the writer (``cardiacfoam.overrides
    ._target_for_parameter``) and the reader
    (``environment._read_config_value_by_key_path``) each independently
    default it to 1, which silently mis-rewrote/mis-read a real multi-block
    document (bathBidomain's three-block ``blockMeshDict.<dim>`` files) --
    the axis's own patch never said how many blocks the record actually
    declared, so both sides fell back to the planners' own ``expected_blocks
    =1`` default regardless.

    ``expected_blocks=1`` produces the bare :data:`HEX_CELL_COUNTS_KEY_PATH`
    unchanged -- the exact spelling a direct ``document:hex_cell_counts``
    study key already sorts to, so an existing single-block record (the
    ``restitutionCurves`` pilot, and any record wired through the axis with
    one block per document) is unaffected byte for byte. A record whose
    ``expected_blocks`` is more than one gets a second segment naming it,
    parsed back out by :func:`hex_cell_counts_expected_blocks`, the one
    place that grammar is written -- shared by the reader and the writer so
    neither can drift from the other, the same "change one, mirror the
    other" warning :func:`read_hex_cell_counts` already gives for
    ``_rewrite_hex_block_lines``'s grammar.
    """
    if expected_blocks == 1:
        return HEX_CELL_COUNTS_KEY_PATH
    return (*HEX_CELL_COUNTS_KEY_PATH, str(expected_blocks))


def hex_cell_counts_expected_blocks(key_path: Sequence[str]) -> int:
    """The ``expected_blocks`` a hex-cell-counts key path carries -- the
    inverse of :func:`hex_cell_counts_key_path`, and the ONE place that
    parse happens: both
    :func:`.environment._read_config_value_by_key_path` and
    :func:`omnidriver.cardiacfoam.overrides._target_for_parameter` call this
    rather than each re-deriving "what does this key path mean" on its own.

    Refuses BY NAME (``ValueError``, naming the key path) when the second
    segment is not a positive integer -- a hand-authored direct study key
    naming a malformed count (e.g. ``document:hex_cell_counts.0`` or
    ``...hex_cell_counts.abc``) is a caller mistake, not a silent 1.

    Only ever called after a caller has already matched this key path's
    leading segment against :data:`HEX_CELL_COUNTS_KEY_PATH` -- a key path
    that is not a hex-cell-counts one at all is not this function's
    concern, and is never passed here.
    """
    segments = tuple(key_path)
    if segments == HEX_CELL_COUNTS_KEY_PATH:
        return 1
    if len(segments) == 2 and segments[0] == HEX_CELL_COUNTS_KEY_PATH[0]:
        try:
            expected_blocks = int(segments[1])
        except ValueError:
            expected_blocks = None
        if expected_blocks is not None and expected_blocks > 0:
            return expected_blocks
    raise ValueError(
        f"{segments!r} is not a hex-cell-counts key path built by "
        "hex_cell_counts_key_path -- expected either "
        f"{HEX_CELL_COUNTS_KEY_PATH!r} (one block) or that plus one "
        "positive-integer segment naming expected_blocks"
    )

def _rewrite_hex_block_lines(
    text: str, cell_counts_str: str, expected_blocks: int, *, label: str,
) -> str:
    """Pure text-level rewrite of every ``hex (`` block declaration in a
    `blockMeshDict` body, factored out of the retired
    `replace_block_mesh_resolutions` writer (Phase 3 Task 4) so the
    resolve/render channel's patch renderer
    (`case_rendering.render_patch_case_files`) reuses this exact grammar
    instead of a second implementation of it -- the same
    "reuse, do not re-implement a dictionary writer" reasoning
    `case_rendering.py`'s module docstring already gives for
    `mutators.update_foam_entry`.

    Reads nothing, writes nothing: `text` in, rewritten text out. Raises
    ``KeyError`` if the number of ``hex (`` lines actually rewritten does not
    equal `expected_blocks` -- silently replacing the wrong number of blocks
    is exactly the failure this function exists to prevent, and this check
    survives being called from either caller (a direct writer, or
    the renderer's snapshot-copy patch). ``label`` is only used to name the
    checked document in that error; the writer passes the real path, the
    renderer passes the case-relative document name -- neither leaks into
    the other's caller.
    """
    lines = text.splitlines(keepends=True)
    rewritten: list[str] = []
    replaced_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("hex (") and not stripped.startswith("//"):
            prefix, _, suffix = line.partition(") (")
            if not suffix:
                rewritten.append(line)
                continue
            _, _, trailing = suffix.partition(") simpleGrading")
            rewritten.append(f"{prefix}) ({cell_counts_str}) simpleGrading{trailing}")
            replaced_count += 1
        else:
            rewritten.append(line)

    if replaced_count != expected_blocks:
        raise KeyError(
            f"Expected to update {expected_blocks} hex blocks in {label}, "
            f"but found {replaced_count}."
        )
    return "".join(rewritten)


def plan_block_mesh_resolution(
    document: str,
    cell_counts_str: str,
    *,
    expected_blocks: int = 1,
) -> Mapping[str, Any]:
    """Resolve a block-mesh-resolution edit into a target
    `case_rendering.render_patch_case_files` understands (Phase 3 Task 4).

    **Why this is not a `ParameterAssignment`.** The plan's own framing:
    rewriting every ``hex (`` line in an existing document is not a
    key/value set -- there is no single `key_path` a caller could name, and
    the number of lines actually rewritten (`expected_blocks`) is itself
    part of what is being asserted, not a value being assigned. Inventing a
    `value_kind` to carry ``hex (`` syntax through `ParameterAssignment`
    would be the `openfoam_literal` layering mistake Phase 2 deliberately
    undid: a kind naming a format inside a vocabulary core owns.
    `ResolvedMutation.targets` is already a loosely-typed
    ``Mapping[str, Any]`` per target, consumed only by
    `case_rendering._document_edits` -- never assumed to be a
    `ParameterAssignment` (see `dict_builder.resolve_synthesis_mutation`'s
    own raw ``{"document", "content", "format"}``/``{"expanded_key_path",
    "value"}`` targets) -- so a target naming this edit's shape needs no
    change to core at all, and no `hex (` knowledge ever reaches it: core
    only ever sees the rendered bytes and their digest.

    Pure: reads nothing, writes nothing, and in particular does **not**
    check `expected_blocks` against a real file -- there is no file to read
    from a resolver that never touches the case. That check is the
    renderer's job (`case_rendering.render_patch_case_files`, which reads
    the real document to build the snapshot it patches), reusing this same
    `_rewrite_hex_block_lines` so the check is asked exactly once, not
    duplicated.

    No `source` field: unlike `ParameterAssignment`, a raw
    `ResolvedMutation` target carries no `VALUE_SOURCES` vocabulary at all
    (`dict_builder.py`'s own synthesis targets carry none either) -- the
    "case vs template" distinction is a property of a *value* a caller
    assigned, and this target assigns no value, only names a structural
    rewrite and the count it must satisfy. There is nothing here for
    `source` to classify.

    `cell_counts_str` is passed through `literals._format_value` for its
    existing `;`/`#`/newline security refusal (SECURITY.md) -- the same
    refusal every other value this channel writes into a dictionary already
    gets, and one the retired direct writer never applied. Reused, not
    re-implemented; it also happens to leave a plain non-bool string like
    ``"80 80 80"`` unchanged, since `_format_value` only special-cases
    `bool` and otherwise returns ``str(value)``.
    """
    return {
        "document": document,
        "format": _patch_format(),
        "hex_cell_counts": _format_value(cell_counts_str),
        "expected_blocks": expected_blocks,
    }


def read_hex_cell_counts(
    document_path: Path, *, expected_blocks: int = 1,
) -> str | None:
    """``ConfigValueCapability``'s reader for the synthetic
    ``HEX_CELL_COUNTS_KEY_PATH`` -- the current cell counts of a
    ``blockMeshDict``'s (single) ``hex (`` block, in the exact same string
    shape :func:`plan_block_mesh_resolution`'s own patch value carries (e.g.
    ``"80 80 80"``), so a study restating the case's own current resolution
    is reported ``unchanged`` by ``tutorial_records.split_unchanged`` rather
    than compared against a differently-shaped answer.

    Mirrors ``_rewrite_hex_block_lines``'s own grammar (a non-comment line
    stripped-starting with ``"hex ("``, split on ``") ("`` then
    ``") simpleGrading"``) rather than sharing code with it: that function
    REWRITES every matching line as it goes and raises through its own
    ``expected_blocks`` check; this one only ever READS, and is called from a
    different capability (`ConfigValueCapability`, not the case-writer
    render path) with no case-relative ``label`` to name in an error the way
    the renderer's caller does. A change to one's grammar must be mirrored in
    the other's.

    ``None`` when ``document_path`` does not exist -- design's own
    "unchanged... never silently reported without a reader to back it"
    posture: an absent document is "cannot determine", not "zero blocks",
    and ``split_unchanged`` already treats a ``None`` current value as
    "changed", never as a false "unchanged".

    Refuses BY NAME (raises ``KeyError``) when other than exactly
    ``expected_blocks`` real ``hex (`` lines are found -- consistent with the
    renderer's own default (``plan_block_mesh_resolution``'s
    ``expected_blocks=1``): a document meant to carry more than one hex block
    (e.g. bathBidomain's three-block ``blockMeshDict.3D``) has no single
    "the" current resolution this reader could report, and reporting one
    block's count while silently ignoring the others would be worse than
    refusing.

    **Also refuses BY NAME when ``expected_blocks`` real blocks disagree**
    (P2, 2026-09-26): this reader answers ONE triple, "the current
    resolution", so when a document genuinely has more than one ``hex ((`` a
    single value is only a truthful answer if every block actually shares
    it -- true of every real multi-block file this reader has been proven
    against (bathBidomain's three ``blockMeshDict.<dim>`` documents, each
    with three blocks all at one resolution), but not guaranteed by this
    reader's own grammar, which never checked before this. Compared as
    whitespace-normalised tokens (``"80  80 80"``/``"80 80 80"`` agree), not
    as raw substrings -- the exact same "typed, not text" posture
    ``apply_overrides.effective_values_agree`` already applies to the
    caller comparing THIS reader's own answer against a requested value.
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = path.read_text()
    counts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("hex (") and not stripped.startswith("//"):
            _prefix, _, suffix = line.partition(") (")
            if not suffix:
                continue
            counts_text, _, _trailing = suffix.partition(") simpleGrading")
            counts.append(counts_text)
    if len(counts) != expected_blocks:
        raise KeyError(
            f"expected {expected_blocks} hex ( block(s) in {path}, found "
            f"{len(counts)}"
        )
    distinct = {tuple(one_count.split()) for one_count in counts}
    if len(distinct) > 1:
        raise KeyError(
            f"{path}'s {len(counts)} hex ( blocks do not share one cell "
            f"count: {sorted(set(counts))!r}"
        )
    return counts[0]


_VERTICES_BLOCK = re.compile(r"vertices\s*\(\s*((?:\([^)]*\)\s*)+)\)\s*;")
_ONE_VERTEX = re.compile(r"\(\s*([^()]*)\)")
#: The keywords ``blockMesh`` reads its scale from, in the order it looks:
#: OpenFOAM v2412 ``blockMesh::readPointTransforms``
#: (``src/mesh/blockMesh/blockMesh/blockMesh.C``) calls
#: ``dict.findCompat("scale", {{"convertToMeters", 1012}})``, and
#: ``dictionary::csearchCompat`` (``src/OpenFOAM/db/dictionary/
#: dictionaryCompat.C``) returns ``scale`` when present and falls back to
#: ``convertToMeters`` only when it is not.
_SCALE_KEYWORDS: tuple[str, ...] = ("scale", "convertToMeters")
_SCALAR = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _scale_line(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{keyword}\s+([^;]*?)\s*;", re.MULTILINE)


def _block_mesh_scale(text: str, path: Path) -> float:
    """The uniform scale ``blockMesh`` applies to ``vertices``: the first of
    :data:`_SCALE_KEYWORDS` present, else 1.0 (no scaling).

    A scalar ``<= 0`` is no scaling, as in ``readScaling`` (same file:
    ``if ((val > 0) && !equal(val, 1))``). ``readScaling`` also takes a
    vector (per-component scaling); this text reader reads a scalar only and
    refuses anything else by name rather than read it as 1.0.

    Added 2026-09-26 (review 54b M5): this read only ``scale``, so a
    dictionary written with ``convertToMeters`` read as scale 1.0, a 1000x
    extent for a millimetre case (at dx 0.5 mm, a silent
    ``(40000, 6000, 14000)``). A ``scale`` line inside a nested
    sub-dictionary would still match first; no native dictionary has one.
    """
    for keyword in _SCALE_KEYWORDS:
        match = _scale_line(keyword).search(text)
        if match is None:
            continue
        value = match.group(1)
        if not _SCALAR.fullmatch(value):
            raise ValueError(
                f"{path}: {keyword!r} is {value!r}; this reader takes a single number "
                "(blockMesh also accepts a per-component vector, which it cannot read)"
            )
        scale = float(value)
        return scale if scale > 0 else 1.0
    return 1.0


def read_hex_block_extent_m(document_path: Path) -> tuple[float, float, float] | None:
    """A ``blockMeshDict``'s own physical bounding-box extent, in METRES:
    the ``vertices`` block's own per-axis ``max - min``, times ``scale``
    (added 2026-09-26, controller review of `2125168`).

    **Why this exists.** `block_mesh_resolution_axis`'s own `resolution`
    callable now also receives this (see that module's own dated
    correction), so a record's resolution formula (e.g.
    `records/niederer_2011.py`'s `dx` axis) can convert a physical cell
    size into cell counts via `mesh_provisioning.cell_counts_from_dx`
    without restating the case's own geometry as a second, independently
    editable Python constant -- "one source of truth" (CLAUDE.md), applied
    to a fact `system/blockMeshDict` already states in its own `vertices`/
    `scale`.

    ``None`` when the document does not exist, or has no ``vertices ( ... );``
    block to parse -- "cannot determine", not "zero extent", the same
    posture :func:`read_hex_cell_counts` already takes for a missing file.
    Every real `blockMeshDict` (this package's own fixtures and every real
    cardiac tutorial's) has one; only a synthetic test fixture that only
    ever exercises cell COUNTS (not extents) reasonably omits it, and such a
    fixture's own `resolution` callable simply never looks at the `extents`
    argument this enables.

    ``scale`` defaults to ``1.0`` when the document declares no `scale`
    line at all (OpenFOAM's own default), not refused -- a `blockMeshDict`
    authored directly in metres is a real, if unusual, case (bidomain's
    unit cubes are). The scale is read as ``blockMesh`` reads it, including
    the ``convertToMeters`` synonym (:func:`_block_mesh_scale`).

    Reads the SAME grammar `_rewrite_hex_block_lines`/`read_hex_cell_counts`
    already parse text-level, never a full OpenFOAM dictionary parser: one
    ``vertices ( (x y z) (x y z) ... );`` block, whitespace-tolerant, no
    nested comments or `#include` expansion (none of this package's own
    `blockMeshDict` grammar handles those either).
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = path.read_text()
    match = _VERTICES_BLOCK.search(text)
    if match is None:
        return None
    scale = _block_mesh_scale(text, path)
    points: list[tuple[float, float, float]] = []
    for vertex_match in _ONE_VERTEX.finditer(match.group(1)):
        tokens = vertex_match.group(1).split()
        if len(tokens) != 3:
            continue
        points.append(tuple(float(token) for token in tokens))  # type: ignore[arg-type]
    if not points:
        return None
    extents = []
    for axis in range(3):
        values = [point[axis] for point in points]
        extents.append((max(values) - min(values)) * scale)
    return tuple(extents)  # type: ignore[return-value]


_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _named_block_body(text: str, name: str) -> str | None:
    """The ``{ ... }`` body of ``name { ... }`` in ``text`` (brace-depth
    aware, so a nested sub-dictionary's own braces do not end the scan
    early), or ``None`` if ``name`` has no such block. The first match
    only -- callers name a scope path one level at a time."""
    match = re.search(rf"(?<![\w.]){re.escape(name)}\s*\{{", text)
    if match is None:
        return None
    depth = 1
    index = match.end()
    while index < len(text) and depth > 0:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    return text[match.end():index - 1]


def read_nested_entry(document_path: Path, key: str, *, scope: Sequence[str]) -> str | None:
    """``key``'s raw value text (trailing ``;`` and inline comments
    stripped) from inside a nested dictionary ``scope`` (e.g.
    ``("monodomainSolverCoeffs", "externalStimulus")``) -- ``None`` when
    the document, any scope block, or the key itself is absent.

    A minimal, read-only nested-block locator in the same house style as
    :func:`read_hex_cell_counts`/:func:`read_hex_block_extent_m` (text-level,
    not a full OpenFOAM dictionary parser) -- deliberately NOT
    ``mutators.read_foam_entry``, which this package's axes/records may
    never import (``scripts/check-case-writes.py`` bans the whole module,
    since it also holds every writer). Strips ``//`` and ``/* */`` comments
    before searching; does not evaluate ``#calc``/``#codeStream`` (returns
    their literal source text, like every other reader here).
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", path.read_text()))
    for name in scope:
        text = _named_block_body(text, name)
        if text is None:
            return None
    match = re.search(rf"(?<![\w.]){re.escape(key)}\s+(.*?);", text, re.DOTALL)
    if match is None:
        return None
    return match.group(1).strip()


def plan_verbatim_content(
    document: str, content: str, *, executable: bool = False,
) -> Mapping[str, Any]:
    """Resolve a whole document's exact bytes into a
    ``render_patch_case_files``/``render_synthesis_case_files`` ``"content"``
    target (Phase 3 Task 7).

    **`executable`** (Phase 3 Task 10): the one property a dictionary
    content target never needed and a hand-runnable script (``Allrun``)
    always does. Both renderers already compute a ``mode`` for a content
    target from the pre-existing file when there is one; ``executable=True``
    tells them to also fold in ``S_IEXEC|S_IXGRP|S_IXOTH`` (0o755 for a
    document that does not exist yet, matching this environment's standard
    022 umask; the existing file's own mode, OR'd with those same bits,
    when one is already there) -- see the ``mode`` computation in each
    renderer for the exact rule. Defaults ``False`` so every pre-existing
    non-executable caller (a dictionary template swapped in verbatim) is
    unaffected.

    **Why this is not a `ParameterAssignment`.** A `ParameterAssignment`
    addresses one key inside a document whose surrounding structure the
    framework does not touch. This function's original motivating case
    (a solver-comparison tutorial, since deleted -- see
    `docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`)
    had no key-level edit at all: its whole-variant documents (e.g.
    ``fvSchemes``, ``fvSolution``, ``controlDict``) were whole, hand-authored
    templates swapped in verbatim -- the differences between variants were
    entire structural blocks, not values at existing keys. Inventing a
    `value_kind` to carry "this document's whole body" through
    `ParameterAssignment` would give one key path a value that is actually
    the entire file, which is not what that type asserts.

    **Not a source artifact either.** A source artifact (see
    `CaseMutationRequest.source_artifacts`) is a *reference* to something a
    mutation consumed -- deliberately opaque and undigested by core, because
    the referenced thing (a mesh, a large asset) may legitimately live
    outside the case and is never itself committed through this channel. A
    template file destined to become `case_root`'s actual
    `electroProperties`/`fvSchemes`/`fvSolution`/`controlDict` is different
    in kind: it is a small, hand-editable OpenFOAM dictionary, exactly the
    class of content this channel already owns end to end (every other
    tutorial's `electroProperties`/`controlDict` reaches `case_root` as a
    `RenderedFile`, not a reference) -- and cardiacFoam reads it downstream
    exactly the way it reads every other tutorial's version of that same
    document. Declaring it a source artifact would carry it out of the
    channel's audit trail (no `content_digest`, no journal-recorded
    before/after bytes) for no reason but its own authoring granularity.

    `document`/`content` become a raw ``{"document", "format", "content"}``
    target -- no `source` field, matching `plan_block_mesh_resolution`'s own
    reasoning: a target that assigns no key/value has nothing for
    `VALUE_SOURCES` to classify. (`plan_dict_block`, which reasoned the same
    way for a whole-sub-dictionary removal, was deleted 2026-09-27 with its
    one caller, the `manufactured_monodomain_pseudo_ecg` tutorial module.)

    **`content` must be `str`, not `bytes` -- checked by running it, not
    assumed.** `ResolvedMutation.__post_init__` deep-freezes every target
    through `case_write._freeze`, which keeps a target JSON-shaped (so a
    resolved plan stays digestible before any renderer runs) and refuses
    `bytes` outright with `TypeError` -- a caller holding raw bytes must
    decode them first (`Path.read_text(encoding="utf-8")` for a UTF-8
    template). The renderer encodes the `str` back with `.encode()` the same
    way `render_synthesis_case_files` already does, so this round-trips
    exactly for any template that was valid UTF-8 to begin with.
    """
    target: dict[str, Any] = {
        "document": document,
        "format": _patch_format(),
        "content": content,
    }
    if executable:
        target["executable"] = True
    return target


def _patch_format() -> str:
    """`case_rendering.FORMAT` -- the one dictionary format every raw
    `render_patch_case_files` target in this module declares, whichever kind
    of edit it carries (`hex_cell_counts`, `dict_operation`, `content`).

    Imported lazily to avoid a module cycle: `case_rendering.py` imports
    `_rewrite_hex_block_lines` from this module at its own module level, so
    this module cannot import `case_rendering` at ITS module level in turn --
    deferred to call time instead, the same way `dict_builder.py` defers
    several of its own cross-module imports for the same reason.
    """
    from .case_rendering import FORMAT

    return FORMAT
