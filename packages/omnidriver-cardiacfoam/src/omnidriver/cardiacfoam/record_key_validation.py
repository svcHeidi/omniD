"""``RecordKeyValidationCapability``'s one composed answer for a cardiac
stack (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §5,
step 4a: "the cardiac stack support that every tutorial record needs before
the first real record exists").

``get_record_key_validator`` is a ``single``-shape composed member
(``provider_stack._SHAPE["get_record_key_validator"] == "single"``): exactly
ONE provider's answer wins for a whole composed stack, most-specific first.
cardiacFOAM is that provider on any stack it joins, so the one function this
module builds must answer for EVERY document such a stack might see -- both
the catalogued cardiac documents (``constant/electroProperties``,
``constant/physicsProperties``) AND the OpenFOAM-owned documents this
package has no catalog for at all (``system/...``) -- not just the cardiac
half. It cannot delegate the OpenFOAM half to the OpenFOAM environment
provider's own answer, because composition never runs two ``single``-shape
answers together.

Three outcomes, exactly the owner's three rules for this task:

1. ``constant/electroProperties`` or ``constant/physicsProperties`` (the two
   documents ``cardiacfoam_plugin.py`` catalogues at all, per
   ``ELECTRO_PROPERTY_ENTRY_GROUPS``/``PHYSICS_PROPERTY_ENTRIES``) -- the
   literal key path is matched against that catalog, reusing
   ``overrides._catalog_entry_for`` (the SAME lookup
   ``resolve_entry_overrides`` already uses, not a second implementation of
   it) for the actual literal-path/dynamic-path matching. A ``<solver>Coeffs``
   first segment stands for the catalog's own ``$ELECTRO_MODEL_COEFFS``
   token; which first-segment spellings are legal is derived from the
   catalog's OWN ``myocardiumSolver`` entry's ``enum_values`` (never a
   hard-coded list -- see ``_myocardium_solver_coeffs_names``). The value is
   then checked against the matched entry's declared ``value_kind`` via
   ``contracts.dictionary.validate_value_shape`` -- shape only, the same
   scope every other consumer of that function stops at (no ``enum_values``
   membership check, no ``applicable_when``/``forbidden_when`` evaluation:
   design step 4a's own wording is "checked against the entry's value_kind
   using the existing shape validation", not the whole catalog semantics).
   ``validated=True``. An uncatalogued key, or a value that does not fit the
   matched entry's declared shape, is refused BY NAME (raises, naming the
   document and key) -- never silently written and never silently given an
   invented kind, the same posture ``resolve_entry_overrides`` already
   established for the override channel.
2. Any other document under ``system/`` -- accepted, ``validated=False``.
   This package owns no OpenFOAM key catalog (design §5's own exception --
   "OpenFOAM-owned keys... have NO catalog today... no partial OpenFOAM
   catalog is to be invented"), so it writes/compares the key as asked with
   no opinion on whether it is a real key the C++ reads, but a genuine
   opinion on its Python-level SHAPE (inferred from the value's own type),
   so the case-value comparator downstream (``CaseValueComparisonCapability``)
   has something typed to work with rather than a placeholder. Note this is
   a deliberate simplification, not an oversight:
   ``common_dict_entries.CONTROL_DICT_ENTRIES`` DOES catalogue
   ``system/controlDict`` keys such as ``deltaT`` -- but for a different
   capability entirely (``run_document_config.py``'s ``--config`` schema,
   the CLI override namespace), not this one. The owner's own instruction
   for this task names ``controlDict`` explicitly as one of the "OpenFOAM-
   owned keys... [with] NO catalog today" for the tutorial-record pipeline,
   and the required native test (``system/controlDict:deltaT`` validates
   ``False``) confirms it: this validator checks only the two ``constant/``
   documents above against a catalog, never ``system/controlDict`` against
   ``CONTROL_DICT_ENTRIES``, even though that catalog exists.
3. Anything else -- refused BY NAME (raises). Deliberate, and closes a real
   hole: without it, a typo like ``constant/electroPropertie`` (missing the
   final ``s``) would fall through as "an OpenFOAM-owned key, unvalidated but
   accepted" instead of being the catalog miss it actually is.

No case root, no filesystem read. The ``<solver>Coeffs`` first-segment
substitution above is a SYNTACTIC and CATALOG-VOCABULARY check only (it
never reads which ``myocardiumSolver`` value is actually active in the
staged case) -- the same as ``overrides._catalog_entry_for``'s own existing
behaviour, which the real ``resolve_entry_overrides`` call sites already
rely on without ever reading the case for this purpose either. Core's
``DirectKeyValidator`` contract (``tutorial_records.py``) was therefore left
unchanged: no staged-case-root parameter was added, because nothing this
validator needs to do requires reading the case.
"""

from __future__ import annotations

from typing import Any

from omnidriver.core.contracts.dictionary import validate_value_shape

from .overrides import _ELECTRO_ENTRIES_BY_PATH, _catalog_entry_for, _validate_dynamic_binding

#: The two documents this package actually catalogues (rule 1). Mirrors
#: ``dict_builder._ELECTRO_DOCUMENT``/``_PHYSICS_DOCUMENT`` (not imported --
#: pulling them in would drag ``dict_builder.py``'s much larger synthesis
#: surface into this small, focused module for two literal strings).
_ELECTRO_DOCUMENT = "constant/electroProperties"
_PHYSICS_DOCUMENT = "constant/physicsProperties"

#: Mirrors ``overrides._COEFFS_TOKEN`` -- both name the same literal
#: ``$ELECTRO_MODEL_COEFFS`` scope token the catalog itself declares in every
#: coeffs-scoped ``DictEntry.driver_path``. Kept as its own literal rather
#: than importing the private name a second time under a different alias:
#: one short string constant duplicated is cheaper than a second private
#: cross-module coupling for the same fact ``overrides.py`` already owns.
_COEFFS_TOKEN = "$ELECTRO_MODEL_COEFFS"


def _myocardium_solver_coeffs_names() -> "frozenset[str]":
    """Every ``<solver>Coeffs`` first-segment spelling the catalog's own
    ``myocardiumSolver`` entry sanctions, derived from its ``enum_values`` --
    never hard-coded (the owner's explicit instruction for this task)."""
    entry = _ELECTRO_ENTRIES_BY_PATH.get("myocardiumSolver")
    if entry is None or not entry.enum_values:
        raise AssertionError(
            "the electroProperties catalog declares no 'myocardiumSolver' "
            "entry (or no enum_values on it) to derive '<solver>Coeffs' "
            "names from -- this is a catalog defect, not a normal refusal"
        )
    return frozenset(f"{value}Coeffs" for value in entry.enum_values)


def _electro_or_physics_match(document: str, key_path: "tuple[str, ...]"):
    """The catalog entry (and any dynamic-path binding) a literal
    ``(document, key_path)`` addresses, or ``None``.

    Reuses ``overrides._catalog_entry_for`` for the actual lookup (a literal
    path, then -- for electroProperties only -- the templated
    ``$ELECTRO_MODEL_COEFFS`` substitution, including its own
    ``match_dynamic_entry`` fallback) rather than re-implementing it, but
    tightens one thing that function's own caller (``resolve_entry_overrides``,
    which trusts an already-detected, currently-active coeffs scope) never
    needed to check: a match reached ONLY via the templated substitution is
    refused unless the concrete first segment is one the catalog's own
    solver vocabulary actually allows. This validator has no trusted,
    already-detected scope to read -- only the literal key path a study
    wrote -- so an arbitrary first segment (e.g. a typo, or a name that is
    not any real ``<solver>Coeffs`` block) must not silently stand in for
    the token the way it would for ``resolve_entry_overrides``' own caller.
    """
    is_electro = document == _ELECTRO_DOCUMENT
    key = key_path[-1]
    scope = key_path[:-1]
    match = _catalog_entry_for(key, scope, is_electro=is_electro)
    if match is None:
        return None
    entry, binding = match
    reached_via_template = (
        is_electro and bool(scope) and entry.driver_path.startswith(f"{_COEFFS_TOKEN}.")
    )
    if reached_via_template and scope[0] not in _myocardium_solver_coeffs_names():
        return None
    return entry, binding


def _infer_unvalidated_value_kind(value: Any) -> str:
    """The best-effort, purely descriptive shape tag for an OpenFOAM-owned
    key this package has no catalog for (rule 2). Never checked against
    anything -- there is no catalog to check it against -- and used
    downstream only by the case-value comparator, which does its own typed
    comparison independent of this tag (``omnidriver.openfoam.apply_overrides
    .effective_values_agree`` dispatches on the requested value's own Python
    type, not on this string).

    ``bool`` is checked before ``int`` because ``bool`` is an ``int``
    subclass in Python -- the same ordering the existing toy validator in
    ``test_tutorial_records.py`` already established for this exact
    "environment-owned-key exception" shape.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    return "word"


def record_key_validator(
    document: str, key_path: "tuple[str, ...]", value: Any,
) -> "tuple[str, bool]":
    """The one callable ``RecordKeyValidationCapability.validator()`` returns
    for a cardiac stack (``CardiacFoamPlugin.get_record_key_validator``).
    See the module docstring for the three rules this implements.
    """
    dotted = ".".join(key_path)
    if document in (_ELECTRO_DOCUMENT, _PHYSICS_DOCUMENT):
        match = _electro_or_physics_match(document, key_path)
        if match is None:
            catalog_name = (
                "electroProperties" if document == _ELECTRO_DOCUMENT else "physicsProperties"
            )
            raise KeyError(
                f"{document}:{dotted} is not declared by the {catalog_name} "
                "key catalog; a key the C++ reads but the catalog lacks is "
                "added to the catalog, never bypassed (design §5)"
            )
        entry, binding = match
        for placeholder, bound_value in binding.items():
            _validate_dynamic_binding(entry, placeholder, bound_value)
        reasons = validate_value_shape(entry.value_kind, value)
        if reasons:
            raise ValueError(
                f"{document}:{dotted} does not fit catalogued value_kind "
                f"{entry.value_kind!r}: {'; '.join(reasons)}"
            )
        return entry.value_kind, True
    if document.startswith("system/"):
        return _infer_unvalidated_value_kind(value), False
    raise KeyError(
        f"{document}:{dotted} is neither a cardiacFOAM-catalogued document "
        f"({_ELECTRO_DOCUMENT!r} or {_PHYSICS_DOCUMENT!r}) nor an "
        "OpenFOAM-owned 'system/' document; refusing rather than silently "
        "treating an unrecognised document as an unvalidated OpenFOAM key"
    )
