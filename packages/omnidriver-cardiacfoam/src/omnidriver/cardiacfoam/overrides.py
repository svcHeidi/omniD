from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from omnidriver.core.case_write import ParameterAssignment
from omnidriver.core.contracts.dictionary import validate_value_shape
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
    ensure_foam_dict,
    remove_foam_dict,
    remove_foam_entry,
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

    **Added 2026-09-23 (Phase 3, the decision closing Task 2's Gap 2):** when
    neither exact lookup matches, try a `dynamic_path` match against the
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

    Three outcomes, per the 2026-09-23 decision:

    - The placeholder is absent from ``entry.allowed_bindings`` entirely --
      refused. This should not happen for any entry this module's catalog
      audit covered (every `dynamic_path` entry in ``dict_entries_catalog.py``
      now declares a domain, open or closed, for each of its placeholders),
      so reaching this branch is itself a catalog gap, not a normal refusal
      path -- and it is refused rather than silently treated as open,
      because an *undeclared* placeholder is exactly audit finding S1's
      hole, not a stated fact an agent can read.
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
#: module has been found passing as an already-rendered OpenFOAM literal
#: rather than typed data. Added to incrementally as each was found
#: (2026-09-23): `dimensioned_scalar`/`dimensioned_tensor` (the decision's
#: own Gap 1), then `vector3`, the four list kinds, and `boolean` (all three
#: corollaries found while closing Gap 2 -- see `_typed_value_for_entry`).
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
#: `mutators._format_value` already renders a plain Python `bool` correctly
#: ("yes"/"no") -- unlike a dimensioned mapping, a vector3 tuple, or a list
#: tuple, which it renders wrong (`str(...)` on the container itself). Adding
#: `boolean` here would change what an already-typed `True`/`False` (e.g.
#: `manufactured_monodomain_pseudo_ecg.py`'s `verificationModel.enabled`,
#: `verificationModel.anisotropic`) renders as, breaking every currently-passing
#: test that asserts "yes"/"no" -- found by running the suite, not assumed.
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

    **Added 2026-09-23 (Phase 3, the decision closing Task 2's Gap 1, plus a
    corollary found while closing it -- see below).** Every real caller of
    this module passes an already-rendered OpenFOAM literal string for a
    `dimensioned_scalar`/`dimensioned_tensor` entry (e.g. ``conductivity``),
    never the ``{"value": ..., "dimensions": ...}`` mapping
    `validate_value_shape` requires -- Phase 2's "typed data" decision
    asserted an adapter already parsed such a string when building its
    request; none ever did. Parsed here, with `literals.parse_dimensioned_literal`
    (owned by ``omnidriver-openfoam``, since OpenFOAM owns this syntax, not
    core and not this adapter).

    The original spelling is kept, not discarded, as this assignment's
    `evidence_refs` -- Gap 1's "the raw spelling is still evidence": the
    transitional writer in `apply_entry_overrides` below uses it verbatim
    when present, rather than a re-rendering that can differ from it in
    ways no OpenFOAM parser cares about (bracket padding, an insignificant
    trailing zero) but a byte-level comparison would (see
    ``omnidriver.openfoam.literals``'s module docstring, and this
    package's ``test_literals.py``).

    **Corollary, found while closing Gap 2, not anticipated by the
    decision:** the same gap exists for `vector3` -- a real catalog entry
    (``ecgDomains.<name>.electrodePositions.<electrode>``) is
    ``value_kind="vector3"`` but a real caller
    (``test_dict_entries_catalog.py``'s
    ``test_apply_electro_property_overrides_updates_dimensioned_and_dynamic_entries``)
    passes it as text (``"(1 2 3)"``), not a Python tuple. Gap 2 alone
    (declaring the dynamic path) makes that override *reach* a catalog
    entry; without this, it would still fail `validate_value_shape` once it
    did. Handled the same way, with `literals.parse_vector3_literal`.
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
    can"). See this task's report for a real instance this newly catches:
    `manufactured_bath_bidomain.py` submits
    ``<solver>Coeffs.manufacturedBidomain.fdaBathVariant``, a key
    `dict_entries_catalog.py`'s own 2026-09-19 correction note says was
    removed because no native code reads it there.

    Every assignment's ``source`` is ``"case"``. This function has no
    fallback of its own -- it only ever sees what its caller already decided
    to pass as ``overrides`` -- so it cannot distinguish a genuine per-case
    choice from a tutorial's own hardcoded default the way
    `dict_builder.py`'s synthesis resolver does (there, by checking
    ``is not None`` at the boundary where the default is actually applied).
    That distinction belongs to each tutorial's own call site, not here; see
    this task's report.

    **Always was, and remains, strict with no fallback of its own** (unlike
    `apply_entry_overrides` below, which had one for one transitional
    release). Two gaps used to make it refuse real overrides that were not
    actually catalog defects: a dynamic per-case identifier
    (``ecgDomains.<name>``, ``conductionNetworkDomains.<name>``,
    ``domainCouplings.<name>``, ...) that `dict_entries_catalog.py` had no
    way to declare, and a `dimensioned_scalar`/`dimensioned_tensor`/
    `vector3`/list/`boolean` entry whose real callers pass an
    already-rendered OpenFOAM literal string, not typed data. Both closed
    2026-09-23: `_catalog_entry_for` now also matches a `dynamic_path`
    template (`_validate_dynamic_binding` checks the binding against the
    entry's own declared domain, open or closed), and `_typed_value_for_entry`
    parses a rendered literal via `omnidriver.openfoam.literals` before this
    function ever sees it.
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

    **Deprecated 2026-09-23 (Phase 3 Task 2).** Delegates to
    `resolve_entry_overrides` for validation and typing, then applies the
    result with `update_foam_entry` -- directly, not through
    `openfoam.case_rendering`'s renderer, because this function has only a
    bare ``file_path`` and no case root to render into and journal against.
    That makes this the one call site in this package still allowed to call
    `update_foam_entry` outside a renderer, kept for one transitional
    release for the sake of a caller outside this repository that already
    depends on this exact signature and write behaviour. Remove this
    direct-write body when no in-tree caller writes through it -- Task 6
    migrates all eleven tutorials that reach this function (via
    `apply_electro_property_overrides` / `apply_physics_property_overrides`)
    onto `resolve_entry_overrides` plus the render/commit channel directly.

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

    **No longer falls back.** Task 2 had to catch `resolve_entry_overrides`'s
    `ValueError` here and re-run the whole batch through the pre-Task-2
    unchecked write, because two catalog/representation gaps made it refuse
    real, currently-passing overrides: a dynamic per-case identifier the
    catalog had no way to declare (`$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.electrodePositions.V1`),
    and a `dimensioned_scalar`/`dimensioned_tensor` (and, found while closing
    the first gap, `vector3`) entry whose real callers pass an
    already-rendered OpenFOAM literal string, never the typed shape
    `validate_value_shape` requires. The 2026-09-23 decision closed both:
    `omnidriver.core.contracts.dictionary.DictEntry.allowed_bindings` can now
    declare a placeholder's domain *open*, explicitly, and this package's
    catalog does so for every `dynamic_path` entry that needs it; and
    `omnidriver.openfoam.literals` parses (and renders) the literal syntax
    Phase 2 assumed already had a parser. With both gaps closed, this
    function now refuses exactly what `resolve_entry_overrides` refuses --
    the same strictness a direct caller (Task 6) already got. A test that
    passed under the fallback and fails now encodes an override the catalog
    genuinely does not declare; see this task's report for the two Phase 2
    tests corrected on exactly that basis.
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
        if assignment.evidence_refs:
            # The original, already-rendered spelling this assignment was
            # parsed from (dimensioned/vector3 kinds only -- see
            # `_typed_value_for_entry`). Writing it verbatim, rather than a
            # re-rendering, preserves bytes a re-rendering is not guaranteed
            # to reproduce (see `omnidriver.openfoam.literals`'s module
            # docstring) and that at least one real test asserts exactly
            # (`test_tet_apply_case_forwards_conductivity_and_advection_approach`).
            # `update_foam_entry` -> `_format_value` still re-applies the
            # `;`/`#`/newline security check to it, same as any value.
            write_value = assignment.evidence_refs[0]
        else:
            # No preserved evidence: this assignment's value arrived already
            # typed (e.g. a real Python `bool`, or a value some future
            # direct caller of `resolve_entry_overrides` constructed itself
            # rather than parsing from text). A container-shaped kind still
            # needs `_CONTAINER_FORMATTERS` to render correctly through
            # `update_foam_entry` -> `_format_value`, which only ever
            # `str()`s an unrecognised type; every other kind (`boolean`
            # included -- see that dict's own docstring) is already
            # `_format_value`'s job.
            render = _CONTAINER_FORMATTERS.get(assignment.value_kind)
            write_value = render(assignment.value) if render is not None else assignment.value
        update_foam_entry(
            file_path,
            assignment.key_path[-1],
            write_value,
            scope=scope,
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


def remove_electro_property_dict(
    electro_properties_path: Path,
    dict_name: str,
    *,
    scope: str | Sequence[str] | None = None,
    missing_ok: bool = False,
) -> None:
    resolved_scope = None
    if scope is not None:
        raw_scope = (scope,) if isinstance(scope, str) else tuple(scope)
        resolved_scope = tuple(
            part
            for token in raw_scope
            for part in _resolve_scope_tokens(
                str(token),
                electro_properties_path=electro_properties_path,
            )
        )

    remove_foam_dict(
        electro_properties_path,
        dict_name,
        scope=resolved_scope,
        missing_ok=missing_ok,
    )


def ensure_electro_property_entry(
    electro_properties_path: Path,
    entry_name: str,
    value: Any,
    *,
    scope: str | Sequence[str] | None = None,
) -> None:
    """Set a scalar entry, adding it if the key is absent.

    The general override path deliberately requires a key to exist already, so
    that a typo fails loudly instead of silently growing a new entry. That is
    the right default, but it cannot express a key whose *presence* legitimately
    varies -- the bath-bidomain patch entries, where which of
    ``groundPatches``/``surfaceCurrentPatches`` holds a patch depends on the
    boundary variant the case was last written for.

    Use this only for such entries. Everything else should stay strict.
    """
    resolved_scope = None
    if scope is not None:
        raw_scope = (scope,) if isinstance(scope, str) else tuple(scope)
        resolved_scope = tuple(
            part
            for token in raw_scope
            for part in _resolve_scope_tokens(
                str(token),
                electro_properties_path=electro_properties_path,
            )
        )

    update_foam_entry(
        electro_properties_path,
        entry_name,
        value,
        scope=resolved_scope,
        add_if_missing=True,
    )


def remove_electro_property_entry(
    electro_properties_path: Path,
    entry_name: str,
    *,
    scope: str | Sequence[str] | None = None,
    missing_ok: bool = False,
) -> None:
    """Scalar counterpart of :func:`remove_electro_property_dict`.

    Same ``$TOKEN`` scope resolution; delegates to
    :func:`~omnidriver.openfoam.mutators.remove_foam_entry` so a
    ``name value;`` entry can be removed without the block remover rejecting
    it for having no opening brace.
    """
    resolved_scope = None
    if scope is not None:
        raw_scope = (scope,) if isinstance(scope, str) else tuple(scope)
        resolved_scope = tuple(
            part
            for token in raw_scope
            for part in _resolve_scope_tokens(
                str(token),
                electro_properties_path=electro_properties_path,
            )
        )

    remove_foam_entry(
        electro_properties_path,
        entry_name,
        scope=resolved_scope,
        missing_ok=missing_ok,
    )


def ensure_electro_property_dict(
    electro_properties_path: Path,
    dict_name: str,
    block_text: str,
    *,
    scope: str | Sequence[str] | None = None,
) -> bool:
    resolved_scope = None
    if scope is not None:
        raw_scope = (scope,) if isinstance(scope, str) else tuple(scope)
        resolved_scope = tuple(
            part
            for token in raw_scope
            for part in _resolve_scope_tokens(
                str(token),
                electro_properties_path=electro_properties_path,
            )
        )

    return ensure_foam_dict(
        electro_properties_path,
        dict_name,
        block_text,
        scope=resolved_scope,
    )


def _resolve_electro_model_coeffs_entry(
    driver_path: str, case_root: Path,
) -> tuple[list[str] | None, str]:
    from .detection import detect_myocardium_solver_name
    from .dict_builder import _entry_scope_and_key

    electro_path = case_root / "constant" / "electroProperties"
    coeffs_scope = f"{detect_myocardium_solver_name(electro_path)}Coeffs"
    return _entry_scope_and_key(driver_path, coeffs_scope)


def electro_model_coeffs_scope() -> "OverrideScope":
    """The cardiac plugin's one `step --strict --apply` override scope:
    $ELECTRO_MODEL_COEFFS -> constant/electroProperties, addressed against
    the "electroProperties" dictionary-catalog group, with the active
    solver's <solver>Coeffs block resolved per-case at apply time."""
    from omnidriver.openfoam.apply_overrides import OverrideScope

    return OverrideScope(
        token="ELECTRO_MODEL_COEFFS",
        file_relpath="constant/electroProperties",
        catalog_group="electroProperties",
        resolve_entry=_resolve_electro_model_coeffs_entry,
    )


def electro_properties_regeneration_scope() -> "RegenerationScope":
    """The cardiac plugin's one `step --strict --apply` regeneration scope:
    the bare ``myocardiumSolver`` selector -> constant/electroProperties,
    rebuilt (not key-patched) via
    :func:`omnidriver.cardiacfoam.dict_builder.regenerate_electro_properties`
    because switching it renames the active ``<solver>Coeffs`` sub-block and
    changes which sibling keys the catalog allows -- something a single
    key/value/scope patch cannot express. Only ``myocardiumSolver`` is
    wired in: the other three ``_SELECTOR_KEYS`` (``ionicModel``,
    ``tissue``, ``conductivitySource``) are ``$ELECTRO_MODEL_COEFFS.``-scoped
    leaves that change a value in place without renaming anything, so they
    stay on the ordinary key-patch route above."""
    from omnidriver.openfoam.apply_overrides import RegenerationScope
    from .dict_builder import regenerate_electro_properties

    return RegenerationScope(
        selector_keys=frozenset({"myocardiumSolver"}),
        file_relpath="constant/electroProperties",
        catalog_group="electroProperties",
        regenerate=regenerate_electro_properties,
    )
