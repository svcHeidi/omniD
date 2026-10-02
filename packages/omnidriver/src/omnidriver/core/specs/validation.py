"""The catalogue's structured rules over a flat ``{slot_key: value}`` context.

Checks required-field omissions, enum violations, and each ``DictEntry``'s
structured constraints (``applicable_when``, ``forbidden_when``,
``required_when``, ``mutually_exclusive_with``, ``co_required_with``),
evaluated once per entry at its *primary* phase -- the first phase in the
adapter-declared order it claims.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterable

from omnidriver.core.contracts.dictionary import DictEntry

if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

from ..planning_types import StrictDiagnostic, diagnostic

def primary_phase(entry, phase_order: tuple[str, ...]) -> str | None:
    """Return the editing phase for a (possibly multi-phase) entry.

    Walks ``phase_order`` -- the ACTIVE PLUGIN's declared phases, from
    ``capabilities.dictionaries.phases()`` -- and returns the first phase the
    entry claims; every other declared phase is a read-only mirror.

    The order is passed in rather than read from a core-declared phase literal
    because that literal spells cardiacFoam's vocabulary. Reading it made every
    entry of a plugin with different phase words return ``None`` here, which the
    required-field and enum checks then treated as "skip".
    """
    for ph in phase_order:
        if ph in entry.phases:
            return ph
    return None


# Any plugin-declared override scope token, not just the built-in cardiac
# plugin's $ELECTRO_MODEL_COEFFS -- this is a syntactic "$TOKEN." shape,
# never resolved to a file or scope path here, so no plugin lookup is
# needed to recognize and strip it.
_SCOPE_TOKEN_PREFIX_RE = re.compile(r"^\$[A-Z][A-Z0-9_]*\.")

# Same generic placeholder shape used by dynamic_path entries themselves
# (see specs/dict_builder.py's _PLACEHOLDER_RE). A condition key can name a
# *sibling* leaf inside the same dynamic block -- e.g.
# ``conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.
# conductionSystemSolver`` gating ``...useEdgeConductance`` in the same
# block -- so predicate keys need the identical wildcard treatment that
# entry driver_paths get, not just the "$SCOPE." prefix.
_PLACEHOLDER_RE = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")


def slot_key(driver_path: str) -> str:
    """Map a driver_path to its slot key inside a phase slice.

    Strips a leading ``$SCOPE_TOKEN.`` prefix when present (any plugin's
    scope token); otherwise returns the path as-is.
    Multi-segment unprefixed paths are kept intact so that nested-group
    leaves don't collide with top-level keys of the same name (e.g.
    ``$ELECTRO_MODEL_COEFFS.bathPotentialDomain.phiEReferenceValue`` must
    not overwrite the top-level ``type`` entry inside the physics slice).
    """
    return _SCOPE_TOKEN_PREFIX_RE.sub("", driver_path, count=1)


def _lookup_slot(mapping: dict[str, Any], driver_path: str):
    """Look up ``driver_path``'s value in a slot mapping, trying both
    legitimate spellings.

    A phase slice (or the flattened context built over every phase slice) may
    key a slot either by the full ``driver_path`` -- an adapter whose
    documents share a leaf name must qualify this way, keeping its document
    scope, see cardiacCore's ``qualified_slot_key`` -- or by the
    scope-stripped ``slot_key`` form, which is what an adapter whose
    documents never collide has always written. Try the full path first,
    then the stripped one, so both spellings resolve correctly without this
    module knowing which one a given adapter chose.
    """
    if driver_path in mapping:
        return mapping[driver_path]
    return mapping.get(slot_key(driver_path))


def _predicate_matches(
    context: dict[str, Any],
    key: str,
    expected: str | tuple[str, ...],
) -> bool:
    """Return True iff ``context[key]`` matches ``expected``.

    Scalar ``expected`` → equality. Tuple ``expected`` → membership.
    A missing key is treated as not-matching (the predicate's
    precondition is absent).

    ``key`` is written in catalog form -- i.e. it may carry a leading
    ``$SCOPE_TOKEN.`` (e.g. ``$ELECTRO_MODEL_COEFFS.``) and, for a
    condition that names a sibling leaf inside a ``dynamic_path`` block
    (e.g. ``conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.
    conductionSystemSolver``), a ``<placeholder>`` segment. ``context``
    keys are ordinarily in resolved slot-key form: prefix stripped, and any
    placeholder replaced by the concrete instance name the caller actually
    configured -- both transforms have to be undone before doing the lookup,
    or an ``applicable_when`` gated on a real driver_path (rather than a bare
    virtual ``$..._present`` token) can never match anything and silently
    evaluates to "not applicable".

    An adapter whose documents share a leaf name may instead key its slice by
    the full, unstripped ``driver_path`` (see cardiacCore's
    ``qualified_slot_key``). ``key`` is tried as given first for that case,
    before falling back to the stripped form; a placeholder condition is not
    affected, since dynamic-path templates are not a qualified-addressing
    concern today.
    """
    resolved_key = slot_key(key)
    if _PLACEHOLDER_RE.search(resolved_key):
        # Sibling-leaf condition inside a dynamic block: the concrete
        # instance name isn't known at this call site (applicability is
        # evaluated once per catalog entry, not once per resolved
        # instance), so treat the placeholder as a wildcard and match if
        # ANY configured instance satisfies the condition.
        pattern = _PLACEHOLDER_RE.sub(r"[^.]+", re.escape(resolved_key))
        regex = re.compile(f"^{pattern}$")
        return any(
            regex.match(ctx_key)
            and ctx_val not in (None, "")
            and _value_matches(ctx_val, expected)
            for ctx_key, ctx_val in context.items()
        )
    if key in context:
        return _value_matches(context[key], expected)
    if resolved_key not in context:
        return False
    return _value_matches(context[resolved_key], expected)


def _value_matches(actual: Any, expected: str | tuple[str, ...]) -> bool:
    """Shared equality/membership check used by ``_predicate_matches``."""
    actual = _normalise_word(actual)
    if isinstance(expected, tuple):
        return actual in tuple(_normalise_word(item) for item in expected)
    return actual == _normalise_word(expected)


def _normalise_word(value: Any) -> Any:
    """Strip one balanced quote pair for catalog comparisons."""
    if not isinstance(value, str) or len(value) < 2:
        return value
    if (value[0], value[-1]) in {('"', '"'), ("'", "'")}:
        return value[1:-1]
    return value


def _entry_is_applicable(entry: DictEntry, context: dict[str, Any]) -> bool:
    """Evaluate ``applicable_when`` and ``forbidden_when`` constraints.

    Returns False if any ``forbidden_when`` predicate matches. Otherwise,
    returns True if all ``applicable_when`` predicates match (or if
    ``applicable_when`` is empty).
    """
    if entry.forbidden_when:
        if any(
            _predicate_matches(context, key, expected)
            for key, expected in entry.forbidden_when.items()
        ):
            return False

    if not entry.applicable_when:
        return True
    return all(
        _predicate_matches(context, key, expected)
        for key, expected in entry.applicable_when.items()
    )


def is_required_in_context(entry: DictEntry, context: dict[str, Any]) -> bool:
    """Whether an entry's ``required`` semantics fire under this context.

    Many entries declare BOTH ``required=True`` and ``required_when={...}``
    — the author's intent is "required, but only when the predicate
    matches". This helper reads the two fields together:

    - ``required_when`` non-empty → required iff any predicate matches.
    - ``required_when`` empty     → ``entry.required`` is taken at face value.
    """
    if entry.required_when:
        return any(
            _predicate_matches(context, key, expected)
            for key, expected in entry.required_when.items()
        )
    return entry.required


def _entry_value_present(entry: DictEntry, context: dict[str, Any]) -> bool:
    """Is the entry's own slot set in the flattened context?

    Tries the entry's own full ``driver_path`` before the scope-stripped
    ``slot_key`` form (see :func:`_lookup_slot`), so a qualified slice is
    read correctly.
    """
    return _lookup_slot(context, entry.driver_path) not in (None, "")


def _format_predicate(predicate: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, expected in predicate.items():
        if isinstance(expected, tuple):
            parts.append(f"{key} ∈ {{{', '.join(expected)}}}")
        else:
            parts.append(f"{key}={expected}")
    return " and ".join(parts)


def validate_context(
    context: dict[str, Any],
    *,
    entries: Iterable[DictEntry] | None = None,
    driver_context: "DriverContext",
) -> tuple[StrictDiagnostic, ...]:
    """Validate a flat ``{slot_key: value}`` context against the catalogue.

    ``entries`` overrides the live catalogue for callers that validate against
    a curated subset (the dictionary builders).
    """
    phase_order = driver_context.capabilities.dictionaries.phases()
    entry_list: list[DictEntry] = (
        list(entries) if entries is not None
        else list(driver_context.capabilities.dictionaries.entries())
    )
    context = {key: val for key, val in context.items() if val not in (None, "")}
    errors: list[StrictDiagnostic] = []

    # Requiredness is conditional on applicability; ``required_when`` narrows
    # ``required`` to the contexts where one of its predicates matches.
    for e in entry_list:
        if not _entry_is_applicable(e, context):
            continue
        if not is_required_in_context(e, context):
            continue
        if e.dynamic_path:
            # A template names no concrete instance, so its required leaves
            # are the resolved-case check's (`run_semantic_validator`).
            continue
        if primary_phase(e, phase_order) is None:
            errors.append(_phase_defect(e, phase_order))
            continue
        if _lookup_slot(context, e.driver_path) in (None, ""):
            errors.append(diagnostic(
                code="run_validation",
                source=primary_phase(e, phase_order),
                field=e.driver_path,
                message=f"{e.driver_path} is required.",
                level="error",
            ))

    for e in entry_list:
        if e.value_kind != "enum" or not e.enum_values:
            continue
        if not _entry_is_applicable(e, context):
            continue
        ph = primary_phase(e, phase_order)
        if ph is None:
            errors.append(_phase_defect(e, phase_order))
            continue
        val = _lookup_slot(context, e.driver_path)
        if val in (None, ""):
            continue
        if _normalise_word(val) not in tuple(_normalise_word(item) for item in e.enum_values):
            errors.append(diagnostic(
                code="run_validation",
                source=ph,
                field=e.driver_path,
                message=f"{val!r} is not one of {list(e.enum_values)}.",
                level="error",
            ))

    errors.extend(_evaluate_structured(entry_list, context, phase_order))
    return tuple(errors)


def _phase_defect(entry: DictEntry, phase_order: tuple[str, ...]) -> StrictDiagnostic:
    """An entry whose phases fall outside the plugin's declared order is a
    catalogue defect, reported rather than skipped."""
    return diagnostic(
        code="run_validation",
        source=phase_order[0] if phase_order else "",
        field=entry.driver_path,
        message=(
            f"{entry.driver_path} declares phases {sorted(entry.phases)}, none "
            f"of which is in the plugin's declared phase order "
            f"{list(phase_order)}. It cannot be validated. Add the "
            f"phase to get_phases() or correct the entry."
        ),
        level="error",
    )


def _evaluate_structured(
    entries: list[DictEntry],
    context: dict[str, Any],
    phase_order: tuple[str, ...],
) -> list[StrictDiagnostic]:
    """Evaluate the five structured-constraint families per entry."""
    errors: list[StrictDiagnostic] = []
    paths_set = {slot_key(e.driver_path) for e in entries
                 if _entry_value_present(e, context)}

    for e in entries:
        ph = primary_phase(e, phase_order) or (phase_order[0] if phase_order else "")

        # forbidden_when: fires when ANY predicate matches AND the entry's
        # own slot has a value. Each matching predicate emits its own
        # diagnostic so the reason text stays specific.
        if _entry_value_present(e, context):
            for key, expected in e.forbidden_when.items():
                if _predicate_matches(context, key, expected):
                    errors.append(diagnostic(
                        level="error",
                        code="run_validation",
                        message=(
                            f"{e.driver_path} is forbidden when "
                            f"{_format_predicate({key: expected})}."
                        ),
                        source=ph,
                        field=e.driver_path,
                    ))

        # Skip entries whose applicable_when/forbidden_when precondition fails
        if not _entry_is_applicable(e, context):
            continue

        # required_when: handled by section 1 of validate_context via
        # is_required_in_context. Section 3 does NOT re-emit a violation
        # to avoid double-firing on the same entry. The structured
        # required_when field is still consumed — its predicates feed
        # is_required_in_context which gates section 1's required check.

        # mutually_exclusive_with: fires when BOTH this entry's slot is set
        # AND any of the listed sibling slots is also set. To avoid
        # double-reporting symmetric relations we only flag the side that
        # *declares* the relation.
        if _entry_value_present(e, context):
            for sibling_path in e.mutually_exclusive_with:
                sibling_slot = slot_key(sibling_path)
                if sibling_slot in paths_set:
                    errors.append(diagnostic(
                        level="error",
                        code="run_validation",
                        message=(
                            f"{e.driver_path} is mutually exclusive with "
                            f"{sibling_path}."
                        ),
                        source=ph,
                        field=e.driver_path,
                    ))

        # co_required_with: the inverse relation. Fires when this entry's
        # slot IS set and a listed sibling's slot is NOT. Unlike
        # mutually_exclusive_with there is no double-reporting to avoid:
        # each unset sibling is a distinct missing value, and declaring the
        # relation on every member of the group is what makes it symmetric.
        if _entry_value_present(e, context):
            for sibling_path in e.co_required_with:
                if slot_key(sibling_path) not in paths_set:
                    errors.append(diagnostic(
                        level="error",
                        code="run_validation",
                        message=(
                            f"{e.driver_path} requires {sibling_path} to be "
                            f"set as well."
                        ),
                        source=ph,
                        field=e.driver_path,
                    ))

    return errors
