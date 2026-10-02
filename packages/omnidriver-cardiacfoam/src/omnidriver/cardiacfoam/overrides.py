from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from omnidriver.core.case_write import (
    CaseMutationRequest,
    ParameterAssignment,
    ResolvedMutation,
)
from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.case_planning import (
    HEX_CELL_COUNTS_KEY_PATH,
    hex_cell_counts_expected_blocks,
    plan_block_mesh_resolution,
)
from omnidriver.openfoam.dict_builder import match_dynamic_entry
from omnidriver.openfoam.literals import (
    format_dimensioned_literal,
    format_integer_list_literal,
    format_scalar_list_literal,
    format_vector3_list_literal,
    format_vector3_literal,
    format_word_list_literal,
    parse_boolean_literal,
    parse_dimensioned_literal,
    parse_integer_list_literal,
    parse_scalar_list_literal,
    parse_vector3_list_literal,
    parse_vector3_literal,
    parse_word_list_literal,
)
from omnidriver.openfoam.mutators import (
    check_dictionary_word_is_safe,
    update_foam_entry,
)
from .detection import detect_electro_coeffs_scope
from .dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from .common_dict_entries import PHYSICS_PROPERTY_ENTRIES

#: This module's identity on every `ParameterAssignment` it produces. Mirrors
#: `dict_builder.PLUGIN_ID` / `runtime_profile._PLUGIN_ID` (both
#: `"org.cardiacfoam"`) rather than importing either: `dict_builder` is a
#: large, otherwise-unrelated module this one has never depended on (its own
#: lazy imports of *this* module, e.g. inside `_resolve_electro_model_coeffs_entry`
#: below, exist specifically to avoid the reverse coupling), and inverting
#: that direction for one string constant would be a worse trade than the
#: duplication. Same value, so a caller comparing owners across this
#: package's `ParameterAssignment`s still sees one identity.
PLUGIN_ID = "org.cardiacfoam"

#: The literal scope token a caller may write in an override path in place of
#: the active `<solver>Coeffs` block name; see `_resolve_scope_tokens`. The
#: catalog (`dict_entries_catalog.py`) declares every electroProperties
#: scoped entry's `driver_path` with this same literal token as its first
#: segment, never with a concrete block name -- that is the abstract address
#: `_catalog_entry_for` below reconstructs from a caller's concrete scope.
_COEFFS_TOKEN = "$ELECTRO_MODEL_COEFFS"

#: driver_path -> DictEntry, one index per document `resolve_entry_overrides`
#: can target. Built once, from the same catalogues `cardiacfoam_plugin.py`
#: aggregates (`ELECTRO_PROPERTY_ENTRY_GROUPS`, `PHYSICS_PROPERTY_ENTRIES`) --
#: not a third, hand-maintained list of the same facts. Kept as two separate
#: indices, not one merged dict, because the templated-path fallback below
#: (a concrete `<solver>Coeffs` first scope segment standing for the literal
#: `$ELECTRO_MODEL_COEFFS` token) is only ever a valid reading for an
#: electroProperties override; letting a physicsProperties lookup fall
#: through to it would validate a physics override against an electro-only
#: catalog entry that happens to share a dotted suffix.
_ELECTRO_ENTRIES_BY_PATH = {
    entry.driver_path: entry
    for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values()
    for entry in group
}
_PHYSICS_ENTRIES_BY_PATH = {
    entry.driver_path: entry for entry in PHYSICS_PROPERTY_ENTRIES
}


def _catalog_entry_for(
    key: str,
    scope: tuple[str, ...],
    *,
    is_electro: bool,
) -> "tuple[DictEntry, dict[str, str]] | None":
    """The `DictEntry` a resolved (scope, key) addresses, plus any dynamic-path
    binding it required to get there, or ``None``.

    Tries the literal, already-resolved path first (what every real tutorial
    call site writes, e.g. ``singleCellSolverCoeffs.tissue``), then -- for an
    electroProperties lookup only, and only when the override is itself
    scoped -- the templated form the catalog actually declares (the first
    scope segment stands for the active `<solver>Coeffs` block, so it is
    replaced with the literal `$ELECTRO_MODEL_COEFFS` token before the second
    lookup). A bare top-level key (``scope`` empty, e.g. ``myocardiumSolver``
    or physicsProperties' ``type``) only ever tries the literal form -- there
    is no coeffs block to substitute.

    When neither exact lookup matches, try a `dynamic_path` match against the
    templated form -- e.g. an override addressing
    ``ecgDomains.ECG.electrodePositions.V1`` reaches here as templated_path
    ``$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.electrodePositions.V1``, which no
    dict lookup finds literally (the catalog's own key is
    ``...ecgDomains.<name>.electrodePositions.<electrode>``), but which
    `match_dynamic_entry` (`omnidriver.openfoam.dict_builder`, reused rather
    than re-implemented -- see that function's own docstring) matches
    positionally, capturing ``{"<name>": "ECG", "<electrode>": "V1"}``. The
    binding is returned unvalidated; `_validate_dynamic_binding` below is
    where it is checked against the entry's declared domain.
    """
    entries = _ELECTRO_ENTRIES_BY_PATH if is_electro else _PHYSICS_ENTRIES_BY_PATH
    literal_path = ".".join((*scope, key))
    entry = entries.get(literal_path)
    if entry is not None:
        return entry, {}
    if is_electro and scope:
        templated_path = ".".join((_COEFFS_TOKEN, *scope[1:], key))
        entry = entries.get(templated_path)
        if entry is not None:
            return entry, {}
        match = match_dynamic_entry(templated_path, entries.values())
        if match is not None:
            return match
    return None


def _validate_dynamic_binding(entry, placeholder: str, bound_value: str) -> None:
    """Refuse a dynamic-path binding the entry's own catalog declaration
    does not sanction.

    Three outcomes:

    - The placeholder is absent from ``entry.allowed_bindings`` entirely --
      refused. This should not happen for any entry this module's catalog
      audit covered (every `dynamic_path` entry in ``dict_entries_catalog.py``
      declares a domain, open or closed, for each of its placeholders), so
      reaching this branch is itself a catalog gap, not a normal refusal
      path -- and it is refused rather than silently treated as open,
      because an *undeclared* placeholder is a hole in the catalog, not a
      stated fact an agent can read.
    - The domain is ``None`` (explicitly open) -- validated as a word: a
      non-empty, whitespace-free string (`validate_value_shape("word", ...)`,
      the same generic shape check core already owns), and free of
      `mutators.check_dictionary_word_is_safe`'s `;`/`#`/newline refusals --
      this binding becomes a dictionary key or sub-block name, never a
      value, so `_format_value`'s own security check (applied only to a
      written value) never sees it otherwise.
    - The domain is a non-empty tuple (closed) -- membership is checked
      directly; no further word/security check is needed, since every
      member of a closed domain is a fixed, already-vetted string.
    """
    if placeholder not in entry.allowed_bindings:
        raise ValueError(
            f"{entry.driver_path!r} declares no binding domain for "
            f"{placeholder!r}; refusing to accept {bound_value!r} rather "
            f"than silently treating an undeclared placeholder as "
            f"unconstrained"
        )
    domain = entry.allowed_bindings[placeholder]
    if domain is None:
        reasons = validate_value_shape("word", bound_value)
        if reasons:
            raise ValueError(
                f"{placeholder!r} bound to {bound_value!r} in "
                f"{entry.driver_path!r}, which is not a valid word: "
                f"{'; '.join(reasons)}"
            )
        check_dictionary_word_is_safe(bound_value)
        return
    if bound_value not in domain:
        raise ValueError(
            f"{placeholder!r} bound to {bound_value!r} in "
            f"{entry.driver_path!r}, which is not one of {list(domain)}"
        )


#: value_kind -> text-to-typed parser, for every kind a real caller of this
#: module passes as an already-rendered OpenFOAM literal rather than typed
#: data -- see `_typed_value_for_entry`.
_TEXT_PARSERS: dict[str, Any] = {
    "dimensioned_scalar": parse_dimensioned_literal,
    "dimensioned_tensor": parse_dimensioned_literal,
    "vector3": parse_vector3_literal,
    "word_list": parse_word_list_literal,
    "scalar_list": parse_scalar_list_literal,
    "integer_list": parse_integer_list_literal,
    "vector3_list": parse_vector3_list_literal,
    # a real caller (manufactured_eikonal_ecg.py's
    # eikonal_advection_diffusion_approach) passes an OpenFOAM Switch
    # spelling ("false") through a `str | None` parameter, not a Python
    # bool -- the same class of gap, found the same way, one kind later.
    "boolean": parse_boolean_literal,
}

#: value_kind -> typed-data-to-text renderer, for use by
#: `apply_entry_overrides`'s transitional writer **only** when it has a
#: typed value with no preserved raw-text evidence (see that function).
#: Deliberately narrower than `_TEXT_PARSERS`: `boolean` is excluded, because
#: `literals._format_value` already renders a plain Python `bool` correctly
#: ("yes"/"no") -- unlike a dimensioned mapping, a vector3 tuple, or a list
#: tuple, which it renders wrong (`str(...)` on the container itself). Adding
#: `boolean` here would change what an already-typed `True`/`False` (e.g.
#: `ecgDomains.<name>.verificationModel.enabled`/`.anisotropic`, direct study
#: keys) renders as, breaking every currently-passing test that asserts
#: "yes"/"no".
_CONTAINER_FORMATTERS: dict[str, Any] = {
    "dimensioned_scalar": format_dimensioned_literal,
    "dimensioned_tensor": format_dimensioned_literal,
    "vector3": format_vector3_literal,
    "word_list": format_word_list_literal,
    "scalar_list": format_scalar_list_literal,
    "integer_list": format_integer_list_literal,
    "vector3_list": format_vector3_list_literal,
}


def _typed_value_for_entry(entry, value: Any) -> "tuple[Any, tuple[str, ...]]":
    """The value to store on a `ParameterAssignment`, plus any raw-text
    evidence to keep alongside it.

    Every real caller of this module passes an already-rendered OpenFOAM
    literal string for a `dimensioned_scalar`/`dimensioned_tensor` entry
    (e.g. ``conductivity``), never the ``{"value": ..., "dimensions": ...}``
    mapping `validate_value_shape` requires. Parsed here, with
    `literals.parse_dimensioned_literal` (owned by ``omnidriver-openfoam``,
    since OpenFOAM owns this syntax, not core and not this adapter).

    The original spelling is kept, not discarded, as this assignment's
    `evidence_refs`: the transitional writer in `apply_entry_overrides` below
    uses it verbatim when present, rather than a re-rendering that can differ
    from it in ways no OpenFOAM parser cares about (bracket padding, an
    insignificant trailing zero) but a byte-level comparison would (see
    ``omnidriver.openfoam.literals``'s module docstring, and this package's
    ``test_literals.py``).

    The same gap exists for `vector3`: a real catalog entry
    (``ecgDomains.<name>.electrodePositions.<electrode>``) is
    ``value_kind="vector3"`` but a real caller passes it as text
    (``"(1 2 3)"``), not a Python tuple. Handled the same way, with
    `literals.parse_vector3_literal`.
    """
    parse = _TEXT_PARSERS.get(entry.value_kind)
    if parse is not None and isinstance(value, str):
        return parse(value), (value,)
    return value, ()


def _resolve_scope_tokens(
    path: str,
    *,
    electro_properties_path: Path | None = None,
) -> tuple[str, ...]:
    resolved_parts: list[str] = []
    for token in path.split("."):
        if token == "$ELECTRO_MODEL_COEFFS":
            if electro_properties_path is None:
                raise ValueError(
                    "Scope token '$ELECTRO_MODEL_COEFFS' requires electro_properties_path"
                )
            resolved_parts.append(detect_electro_coeffs_scope(electro_properties_path))
            continue
        resolved_parts.append(token)
    return tuple(part for part in resolved_parts if part)


def normalize_entry_overrides(
    overrides: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    electro_properties_path: Path | None = None,
) -> list[dict[str, Any]]:
    if overrides is None:
        return []

    def normalize_from_key_value(key_path: str, value: Any) -> dict[str, Any]:
        parts = _resolve_scope_tokens(
            str(key_path),
            electro_properties_path=electro_properties_path,
        )
        if not parts:
            raise ValueError("Override path cannot be empty")
        if len(parts) == 1:
            return {"key": parts[0], "value": value, "scope": None}
        return {"key": parts[-1], "value": value, "scope": parts[:-1]}

    if isinstance(overrides, Mapping):
        return [normalize_from_key_value(key_path, value) for key_path, value in overrides.items()]

    normalized: list[dict[str, Any]] = []
    for item in overrides:
        if not isinstance(item, Mapping):
            raise TypeError("Entry overrides must be a mapping or sequence of mappings")
        if "key" not in item or "value" not in item:
            raise KeyError("Override items must define 'key' and 'value'")

        key = str(item["key"])
        value = item["value"]
        if "scope" in item:
            raw_scope = item["scope"]
            if raw_scope is None:
                scope = None
            elif isinstance(raw_scope, str):
                scope = _resolve_scope_tokens(
                    raw_scope,
                    electro_properties_path=electro_properties_path,
                )
            else:
                scope = tuple(
                    part
                    for token in raw_scope
                    for part in _resolve_scope_tokens(
                        str(token),
                        electro_properties_path=electro_properties_path,
                    )
                )
        else:
            normalized_item = normalize_from_key_value(key, value)
            normalized.append(normalized_item)
            continue

        normalized.append(
            {
                "key": key,
                "value": value,
                "scope": scope,
            }
        )

    return normalized


def resolve_entry_overrides(
    file_path: Path,
    overrides: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    document: str,
    electro_properties_path: Path | None = None,
) -> tuple[ParameterAssignment, ...]:
    """Resolve entry overrides into typed, catalog-validated assignments.

    Pure: reads nothing from ``file_path`` beyond what ``normalize_entry_overrides``
    already needs (detecting the active `<solver>Coeffs` scope, when
    ``electro_properties_path`` is given, to expand a ``$ELECTRO_MODEL_COEFFS``
    token) and writes nothing. ``document`` is supplied by the caller, not
    derived here: this function has no case root to make a path relative to,
    so a genuine case-relative document (e.g. ``"constant/electroProperties"``)
    is the caller's to know, not this function's to guess.

    ``electro_properties_path is not None`` is also the signal for which
    catalog to validate against -- it is true exactly when this call
    addresses electroProperties (``apply_electro_property_overrides`` always
    passes it; ``apply_physics_property_overrides`` never does), so it is
    reused here rather than adding a second, redundant "which document"
    parameter.

    Each override's ``value_kind`` comes from the matching `DictEntry` --
    never guessed. **An override naming a key the catalog does not declare is
    refused (`ValueError`)**, not silently written and not silently given an
    invented kind: this mirrors the precedent already established by
    `cardiaccore.workflows.overrides.validate_input_overrides` ("a key absent
    from the catalog is one no native utility reads... writing such a key is
    a silent no-op -- the one failure the solver cannot report and this layer
    can").

    Every assignment's ``source`` is ``"case"``. This function has no
    fallback of its own -- it only ever sees what its caller already decided
    to pass as ``overrides`` -- so it cannot distinguish a genuine per-case
    choice from a tutorial's own hardcoded default the way
    `dict_builder.py`'s synthesis resolver does (there, by checking
    ``is not None`` at the boundary where the default is actually applied).
    That distinction belongs to each tutorial's own call site, not here.

    **Strict, with no fallback of its own** (unlike `apply_entry_overrides`
    below, which had one for one transitional release): `_catalog_entry_for`
    also matches a `dynamic_path` template for a dynamic per-case identifier
    (``ecgDomains.<name>``, ``conductionNetworkDomains.<name>``,
    ``domainCouplings.<name>``, ...), with `_validate_dynamic_binding`
    checking the binding against the entry's own declared domain, and
    `_typed_value_for_entry` parses a `dimensioned_scalar`/`dimensioned_tensor`/
    `vector3`/list/`boolean` entry's already-rendered OpenFOAM literal string
    via `omnidriver.openfoam.literals` before this function ever sees it.
    """
    is_electro = electro_properties_path is not None
    assignments = []
    for item in normalize_entry_overrides(
        overrides,
        electro_properties_path=electro_properties_path,
    ):
        key = item["key"]
        scope = item["scope"] or ()
        key_path = (*scope, key)
        match = _catalog_entry_for(key, scope, is_electro=is_electro)
        if match is None:
            raise ValueError(
                f"override {'.'.join(key_path)!r} is not declared by the "
                f"{'electroProperties' if is_electro else 'physicsProperties'} "
                f"catalog; no native utility is known to read an undeclared "
                f"key, so writing it would be a silent no-op the catalog "
                f"exists to catch"
            )
        entry, binding = match
        for placeholder, bound_value in binding.items():
            _validate_dynamic_binding(entry, placeholder, bound_value)
        typed_value, evidence_refs = _typed_value_for_entry(entry, item["value"])
        assignments.append(ParameterAssignment(
            qualified_id=".".join(key_path),
            owner=PLUGIN_ID,
            document=document,
            key_path=key_path,
            binding={},
            value=typed_value,
            value_kind=entry.value_kind,
            source="case",
            evidence_refs=evidence_refs,
        ))
    return tuple(assignments)


def apply_entry_overrides(
    file_path: Path,
    overrides: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    electro_properties_path: Path | None = None,
) -> None:
    """Write entry overrides directly into ``file_path``.

    Delegates to `resolve_entry_overrides` for validation and typing, then
    applies the result with `update_foam_entry` -- directly, not through
    `openfoam.case_rendering`'s renderer, because this function has only a
    bare ``file_path`` and no case root to render into and journal against.
    That makes this the one call site in this package still allowed to call
    `update_foam_entry` outside a renderer, kept for a caller outside this
    repository that depends on this exact signature and write behaviour.

    ``document`` is not a parameter here (unlike `resolve_entry_overrides`):
    this function's only caller-facing identity for the file it writes is
    ``file_path`` itself, which may be any path, not necessarily one that
    is genuinely relative to a case root this function knows about. Rather
    than invent a ``"constant/"`` prefix no ambient state confirms (see this
    repository's supplied-vs-discovered rule), ``file_path.name`` alone is
    used -- a single path segment, always case-relative by construction,
    that costs nothing because nothing downstream in this transitional path
    reads `ParameterAssignment.document` for anything but its own
    constructor check.

    **No fallback.** This function refuses exactly what
    `resolve_entry_overrides` refuses:
    `omnidriver.core.contracts.dictionary.DictEntry.allowed_bindings` can
    declare a placeholder's domain *open*, explicitly, for a dynamic
    per-case identifier, and `omnidriver.openfoam.literals` parses (and
    renders) an already-rendered OpenFOAM literal string for a
    `dimensioned_scalar`/`dimensioned_tensor`/`vector3` entry.
    """
    document = Path(file_path).name
    assignments = resolve_entry_overrides(
        file_path,
        overrides,
        document=document,
        electro_properties_path=electro_properties_path,
    )

    for assignment in assignments:
        scope = assignment.key_path[:-1] or None
        update_foam_entry(
            file_path,
            assignment.key_path[-1],
            _write_value_for_assignment(assignment),
            scope=scope,
        )


def _write_value_for_assignment(assignment: ParameterAssignment) -> Any:
    """The raw value that must actually reach `update_foam_entry` for
    `assignment` to write the same bytes `apply_entry_overrides` always has.
    Reused, not duplicated, by `resolve_patch_mutation` below, which needs
    the identical mapping to give the render/commit channel the same bytes
    as the direct writer.

    If `assignment.evidence_refs` is non-empty, that is the original,
    already-rendered spelling this assignment was parsed from
    (dimensioned/vector3 kinds only -- see `_typed_value_for_entry`).
    Writing it verbatim, rather than a re-rendering, preserves bytes a
    re-rendering is not guaranteed to reproduce (see
    `omnidriver.openfoam.literals`'s module docstring) and that at least one
    real test asserts exactly
    (`test_tet_apply_case_forwards_conductivity_and_advection_approach`).
    `update_foam_entry` -> `_format_value` still re-applies the `;`/`#`/
    newline security check to it, same as any value.

    Otherwise, `assignment.value` arrived already typed (e.g. a real Python
    `bool`, or a value some direct caller of `resolve_entry_overrides`
    constructed itself rather than parsing from text). A container-shaped
    kind still needs `_CONTAINER_FORMATTERS` to render correctly through
    `update_foam_entry` -> `_format_value`, which only ever `str()`s an
    unrecognised type; every other kind (`boolean` included -- see that
    dict's own docstring) is already `_format_value`'s job.
    """
    if assignment.evidence_refs:
        return assignment.evidence_refs[0]
    render = _CONTAINER_FORMATTERS.get(assignment.value_kind)
    return render(assignment.value) if render is not None else assignment.value


def _target_for_parameter(parameter: ParameterAssignment) -> dict[str, Any]:
    """One `render_patch_case_files` edit target for `parameter` -- a
    parameter asserts a final state, not only a value.

    **The hex-rewrite target.** A parameter whose `key_path` is
    `case_planning.HEX_CELL_COUNTS_KEY_PATH` (`block_mesh_resolution_axis`'s
    synthetic key -- see that module's own docstring) is not an ordinary
    key/value edit: it is `plan_block_mesh_resolution`'s own structural
    `"hex_cell_counts"`/`"expected_blocks"` shape, not `"expanded_key_path"`/
    `"value"`, since it would otherwise SET a literal top-level dictionary
    key named `hex_cell_counts`, never rewriting a single `hex (` line.
    `parameter.value` is the axis's own typed tuple of ints; this
    reconstructs the exact space-joined text `plan_block_mesh_resolution`
    expects, reusing that planner rather than re-implementing its formatting
    or security check.

    A `remove` carries no `"value"` key: there is nothing to format (its
    `value` is `None`, refused as a value to write), and
    `render_patch_case_files` never reads `"value"` for a `remove` edit --
    matching the hex-rewrite target's own shape, which also carries no
    `"value"`, for the same reason. Every other operation keeps writing
    `_write_value_for_assignment`'s result.

    **The block count travels with the patch.** `expected_blocks` is read
    from `parameter`, not assumed to be `plan_block_mesh_resolution`'s own
    `expected_blocks=1` default: a multi-block document (bathBidomain's
    three-block `blockMeshDict.<dim>` files) would otherwise raise
    "Expected to update 1 hex blocks, but found 3" no matter what the axis
    resolved. `hex_cell_counts_expected_blocks` parses the count
    `case_planning.hex_cell_counts_key_path` encoded into `parameter.key_path`
    when the axis built it, so this writer honours whatever the record
    actually stated instead of guessing 1.
    """
    if parameter.key_path[:1] == HEX_CELL_COUNTS_KEY_PATH:
        expected_blocks = hex_cell_counts_expected_blocks(parameter.key_path)
        cell_counts_str = " ".join(str(count) for count in parameter.value)
        return dict(plan_block_mesh_resolution(
            parameter.document, cell_counts_str, expected_blocks=expected_blocks,
        ))
    target: dict[str, Any] = {
        "qualified_id": parameter.qualified_id,
        "document": parameter.document,
        "expanded_key_path": list(parameter.expanded_key_path()),
        "operation": parameter.operation,
        "format": case_rendering.FORMAT,
    }
    if parameter.operation != "remove":
        target["value"] = _write_value_for_assignment(parameter)
    return target


def resolve_patch_mutation(request: CaseMutationRequest) -> ResolvedMutation:
    """The semantic owner's answer for a `clone_and_patch` request.

    Mirrors `cardiaccore.workflows.overrides.resolve_patch_mutation` in
    shape -- pure, every parameter already addressed by the caller
    (`resolve_entry_overrides`) before this ever runs. The one real
    difference: `target["value"]` is `_write_value_for_assignment(parameter)`,
    not `parameter.value` (the typed value) the way cardiacCore's resolver
    uses directly. cardiacCore's own parameters carry no `evidence_refs` and
    need no container formatting, so `parameter.value` already IS the write
    value there; this package's do, so writing `parameter.value` unmodified
    through `case_rendering.render_patch_case_files`'s generic
    `update_foam_entry(..., edit["value"], ...)` would not reproduce
    `apply_entry_overrides`'s bytes for a dimensioned/vector3/list kind.

    **Carries `parameter.operation` through.** A `remove` parameter has no
    value to format (`ParameterAssignment.__post_init__` refuses one) --
    `_write_value_for_assignment` is not called for it, and its target
    carries no `"value"` key at all, matching the hex-rewrite target's own
    shape (no `"value"` either, for the same reason: nothing to write).
    `render_patch_case_files` reads `target["operation"]`, defaulting to
    `"set"`.
    """
    if request.mode != "clone_and_patch":
        raise ValueError(
            f"cardiacFoam's overrides workflow resolves clone_and_patch "
            f"requests only, not {request.mode!r}"
        )
    targets = tuple(_target_for_parameter(parameter) for parameter in request.parameters)
    expected_effects = tuple(
        f"{parameter.operation} {parameter.qualified_id!r} in {parameter.document}"
        for parameter in request.parameters
    )
    return ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=expected_effects, semantic_owner_id=PLUGIN_ID,
    )


def apply_electro_property_overrides(
    electro_properties_path: Path,
    overrides: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> None:
    apply_entry_overrides(
        electro_properties_path,
        overrides,
        electro_properties_path=electro_properties_path,
    )


def apply_physics_property_overrides(
    physics_properties_path: Path,
    overrides: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> None:
    apply_entry_overrides(physics_properties_path, overrides)
