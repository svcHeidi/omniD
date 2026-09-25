"""Pure OpenFOAM case-edit planners -- no writer lives here (review finding
M2, the ``utils.py`` split).

Every function in this module reads nothing and writes nothing: each
resolves a requested edit into a typed, pure target (a
``ParameterAssignment`` or a raw ``render_patch_case_files`` target mapping)
for the render/commit channel to act on later. ``utils.py`` keeps this
module's writer counterparts (``set_delta_t`` and kin) -- the two used to
live in the same module, which made it impossible for a tutorial-record axis
to import a pure planner without ALSO being able to reach a writer one
import away. A future axis module (``openfoam/axes/``) may import from here;
``scripts/check-case-writes.py`` bans importing ``omnidriver.openfoam.utils``
entirely from that directory, but this module is never named there.
"""

from collections.abc import Sequence
from typing import Any, Mapping

from omnidriver.core.case_write import ParameterAssignment

from .literals import _format_value

#: `system/controlDict` is a fixed, case-relative location -- the same for
#: every OpenFOAM case, never derived from a caller-supplied path. Unlike
#: `cardiacfoam.overrides.resolve_entry_overrides` (which takes `document`
#: from its caller because it has only a bare `file_path` and no case root
#: to make one relative to), `plan_delta_t`/`plan_end_time` need no path
#: argument at all: they are pure and address this document by name alone.
_CONTROL_DICT_DOCUMENT = "system/controlDict"


def plan_delta_t(delta_t_seconds: float, *, owner: str) -> ParameterAssignment:
    """Resolve a `system/controlDict` `deltaT` edit into a typed, pure
    `ParameterAssignment` -- reads nothing, writes nothing (Phase 3 Task 3).

    Beside `utils.set_delta_t`, not a replacement for it yet: that function
    keeps writing directly until its last caller migrates onto the
    render/commit channel.

    ``owner`` is supplied, not discovered: this module (`omnidriver-openfoam`)
    must not know about cardiacFoam or any other adapter identity (see this
    repository's package table -- `omnidriver-openfoam` "must not know about
    cardiology"), so unlike `dict_builder.py`'s own controlDict-touching
    code, which hardcodes its own `PLUGIN_ID`, this function cannot supply a
    default of its own; the caller's adapter id is the caller's to know.

    ``source`` is unconditionally ``"case"``: unlike `dict_builder.py`'s
    synthesis resolver (which chooses `"case"` vs `"template"` depending on
    whether ITS OWN caller passed `None` and it fell back to a built-in
    default), this function takes no default path of its own -- it has no
    optional parameter and no fallback, so every value it sees is one a
    caller explicitly decided to assign. Matches the same reasoning
    `cardiacfoam.overrides.resolve_entry_overrides` gives for the same
    conclusion.

    No `evidence_refs`: verified against all eleven real tutorial call
    sites (`grep -rn "set_delta_t\\|set_end_time"
    packages/omnidriver-cardiacfoam/src/.../tutorials/`) that every one
    passes an already-native Python `float`, never an already-rendered
    OpenFOAM literal string -- unlike the `dimensioned_scalar`/`vector3`
    entries Task 2's Gap 1 found, a bare `controlDict` scalar has no
    OpenFOAM-specific literal syntax to parse (no dimension brackets), so
    `omnidriver.openfoam.literals` does not apply here and there is no
    original rendered spelling to preserve as evidence.

    **The value is passed through untouched, not coerced with `float()`.**
    A non-`Real` (a string included -- there is no parser for it to go
    through, per the paragraph above) is refused by `ParameterAssignment`'s
    own construction-time `validate_value_shape` check, the same guard every
    other `scalar` declaration gets. Coercing here instead would silently
    swallow a caller's mistake (or a genuine rendered literal this function
    has no business accepting) rather than refusing it -- the same
    strict-resolver posture the fallback deletion established for the
    override channel.
    """
    return ParameterAssignment(
        qualified_id="deltaT",
        owner=owner,
        document=_CONTROL_DICT_DOCUMENT,
        key_path=("deltaT",),
        binding={},
        value=delta_t_seconds,
        value_kind="scalar",
        source="case",
    )


def plan_end_time(t_s: float, *, owner: str) -> ParameterAssignment:
    """`plan_delta_t`'s counterpart for `endTime` -- see its docstring for
    the `owner`/`source`/evidence reasoning, which applies identically."""
    return ParameterAssignment(
        qualified_id="endTime",
        owner=owner,
        document=_CONTROL_DICT_DOCUMENT,
        key_path=("endTime",),
        binding={},
        value=t_s,
        value_kind="scalar",
        source="case",
    )


def plan_write_interval(t_s: float, *, owner: str) -> ParameterAssignment:
    """`plan_end_time`'s counterpart for `writeInterval` (Phase 3 Task 6's
    completion, 2026-09-23). Real caller:
    `manufactured_bath_bidomain._apply_case`, which sets `writeInterval` to
    the same value as `endTime` whenever an explicit `end_time` is given --
    `writeControl` there is `adjustableRunTime` (time-based, not
    step-count-based), so a temporal-convergence sweep's writeInterval must
    track an overridden endTime or it stays pinned to the checked-in default
    and stops matching. Same `owner`/`source`/evidence reasoning as
    `plan_delta_t`/`plan_end_time`; `operation` defaults to `"set"`, matching
    that tutorial's own direct call (`update_foam_entry(control_dict,
    "writeInterval", end_time)`, no `add_if_missing`)."""
    return ParameterAssignment(
        qualified_id="writeInterval",
        owner=owner,
        document=_CONTROL_DICT_DOCUMENT,
        key_path=("writeInterval",),
        binding={},
        value=t_s,
        value_kind="scalar",
        source="case",
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


def plan_dict_block(
    document: str,
    dict_name: str,
    *,
    operation: str,
    scope: Sequence[str] | None = None,
    block_text: str | None = None,
) -> Mapping[str, Any]:
    """Resolve a whole-sub-dictionary insert/removal into a
    ``render_patch_case_files`` target (Phase 3 Task 6's completion,
    2026-09-23) -- the counterpart of :func:`plan_block_mesh_resolution` for
    :func:`mutators.ensure_foam_dict`/:func:`mutators.remove_foam_dict`
    instead of the ``hex (`` rewrite.

    **Why this is not a `ParameterAssignment`**, same reasoning as
    `plan_block_mesh_resolution`'s own docstring: there is no single
    ``key_path`` a typed value sits at. ``block_text`` (``operation="ensure"``
    only) is a whole hand-authored sub-dictionary body -- e.g.
    `manufactured_bath_bidomain`'s ``ecgDomains`` block, several nested
    sub-dictionaries deep -- and inventing a `value_kind` to carry that
    through core's typed-value vocabulary would be the same layering mistake
    the hex case already rejects. ``operation="remove"`` needs no value at
    all, matching a `ParameterAssignment` `remove`'s own "nothing to write"
    shape, but still is not one: `ParameterAssignment.key_path` addresses one
    leaf entry with a declared `value_kind`; a whole sub-dictionary has
    neither.

    Pure: reads nothing, writes nothing. ``render_patch_case_files`` is
    where ``ensure_foam_dict``/``remove_foam_dict`` actually run, against the
    snapshot copy, the same "resolver never touches the case" split every
    other target in this module keeps.

    ``scope`` is passed through as given (already-resolved segments, e.g.
    an active ``<solver>Coeffs`` block name) -- unlike
    `cardiacfoam.overrides._resolve_scope_tokens`, this module owns no
    ``$ELECTRO_MODEL_COEFFS``-style token vocabulary; a caller resolves its
    own tokens before calling this, the same division
    `plan_block_mesh_resolution` already has (no cardiac vocabulary here).
    """
    if operation not in {"ensure", "remove"}:
        raise ValueError(
            f"dict block target {dict_name!r} in {document!r} declares "
            f"operation {operation!r}; known operations are 'ensure' and "
            f"'remove'"
        )
    if operation == "ensure" and block_text is None:
        raise ValueError(
            f"dict block target {dict_name!r} in {document!r} declares "
            f"operation 'ensure' but no block_text; there is nothing to "
            f"insert"
        )
    target: dict[str, Any] = {
        "document": document,
        "format": _patch_format(),
        "dict_operation": operation,
        "dict_name": dict_name,
        "scope": list(scope) if scope else None,
    }
    if operation == "ensure":
        target["block_text"] = block_text
    return target


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
    target -- no `source` field, matching `plan_block_mesh_resolution`'s and
    `plan_dict_block`'s own reasoning: a target that assigns no key/value has
    nothing for `VALUE_SOURCES` to classify.

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
