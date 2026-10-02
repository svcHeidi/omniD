"""``RecordKeyValidationCapability``'s one composed answer for a cardiac
stack.

``get_record_key_validator`` is a ``single``-shape composed member: exactly
one provider's answer wins for a whole composed stack, most-specific first.
cardiacFOAM is that provider on any stack it joins, so the one function this
module builds must answer for EVERY document such a stack might see -- both
the catalogued cardiac documents (``constant/electroProperties``,
``constant/physicsProperties``) AND the OpenFOAM-owned documents this
package has no catalog for at all (``system/...``), not just the cardiac
half. It cannot delegate the OpenFOAM half to the OpenFOAM environment
provider's own answer, because composition never runs two ``single``-shape
answers together.

Three outcomes:

1. ``constant/electroProperties`` or ``constant/physicsProperties`` -- the
   literal key path is matched against that catalog, reusing
   ``overrides._catalog_entry_for`` (the same lookup ``resolve_entry_overrides``
   already uses) for the literal-path/dynamic-path matching. A
   ``<solver>Coeffs`` first segment stands for the catalog's own
   ``$ELECTRO_MODEL_COEFFS`` token; which first-segment spellings are legal
   is derived from the catalog's own ``myocardiumSolver`` entry's
   ``enum_values`` (never a hard-coded list -- see
   ``_myocardium_solver_coeffs_names``). The value is then checked against
   the matched entry's declared ``value_kind`` via
   ``contracts.dictionary.validate_value_shape`` -- shape only, no
   ``enum_values`` membership check, no ``applicable_when``/``forbidden_when``
   evaluation. ``validated=True``. A key the catalogue lacks is accepted
   only when the supplied C++ source reads it
   (``omnidriver.openfoam.record_key_validation.scanned_key``), validated
   by the scanned type; any other uncatalogued key, or a value that does not
   fit its shape, is refused by name. A map at a key whose members the catalogue declares as one
   dynamic ``<name>`` segment (``bathPotentialDomain.groundPatches.<patch>``)
   is checked member by member against that entry and validates as
   ``"mapping"``; the writer replaces the whole sub-dictionary with it.
2. Any other document under ``system/`` -- accepted, ``validated=False``.
   This package owns no OpenFOAM key catalog, so it writes/compares the key
   as asked with no opinion on whether it is a real key the C++ reads, but a
   genuine opinion on its Python-level shape (inferred from the value's own
   type), so the case-value comparator downstream
   (``CaseValueComparisonCapability``) has something typed to work with
   rather than a placeholder. Deliberate, not an oversight:
   ``common_dict_entries.CONTROL_DICT_ENTRIES`` does catalogue
   ``system/controlDict`` keys such as ``deltaT``, but for a different
   capability (``run_document_config.py``'s ``--config`` schema), not this
   one -- this validator checks only the two ``constant/`` documents above
   against a catalog, never ``system/controlDict`` against
   ``CONTROL_DICT_ENTRIES``.

   ``_infer_unvalidated_value_kind`` infers ``integer_list``/``scalar_list``
   for a plain ``list``/``tuple``, in addition to ``bool``/``int``/``float``
   (falling back to ``"word"``): a ``system/``-owned key can be a real,
   committed typed multi-value (e.g. from ``block_mesh_resolution_axis``),
   not only a pre-joined space-separated string.
3. Anything else -- refused by name. Deliberate, and closes a real hole:
   without it, a typo like ``constant/electroPropertie`` (missing the final
   ``s``) would fall through as "an OpenFOAM-owned key, unvalidated but
   accepted" instead of being the catalog miss it actually is.

**The catalogue** (``record_key_catalog``) is the same three rules, listed
for one case so an agent can read them
(``SolverPlugin.get_record_key_catalog``; the grammar is core's
``runtime.record_surface``): rule 1's two catalogues, with the case's own
``<solver>Coeffs`` in place of ``$ELECTRO_MODEL_COEFFS``; rule 2's
``system/`` documents, each listed once as open (``validated: False``); and,
by omission, rule 3. It reads the case; the validator below does not.

No case root, no filesystem read. The ``<solver>Coeffs`` first-segment
substitution above is a syntactic and catalog-vocabulary check only (it
never reads which ``myocardiumSolver`` value is actually active in the
staged case) -- the same as ``overrides._catalog_entry_for``'s own existing
behaviour. Core's ``DirectKeyValidator`` contract was therefore left
unchanged: no staged-case-root parameter was added, because nothing this
validator needs to do requires reading the case.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pathlib import Path

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.runtime.record_surface import ANY_KEY
from omnidriver.openfoam.record_key_validation import infer_unvalidated_value_kind, listed_entry, scanned_key

from .detection import detect_myocardium_solver_name
from .overrides import (
    _ELECTRO_ENTRIES_BY_PATH, _PHYSICS_ENTRIES_BY_PATH, _catalog_entry_for, _validate_dynamic_binding,
)
from .physics_layout import PhysicsLayoutError, region_of

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


def _declares_members(document: str, key_path: "tuple[str, ...]") -> bool:
    """Whether the catalog declares ``key_path``'s members as one dynamic
    segment, i.e. has an entry ``<key_path>.<name>``. Checked on the
    catalog's own paths, so it holds for an empty map too."""
    if document != _ELECTRO_DOCUMENT:
        return False
    parent = ".".join(key_path)
    if len(key_path) > 1 and key_path[0] in _myocardium_solver_coeffs_names():
        parent = ".".join((_COEFFS_TOKEN,) + tuple(key_path[1:]))
    return any(
        entry.dynamic_path and path.rpartition(".")[0] == parent
        and path.rpartition(".")[2].startswith("<")
        for path, entry in _ELECTRO_ENTRIES_BY_PATH.items()
    )


#: Shared with cardiacCore's own ``system/`` documents validator via
#: ``omnidriver-openfoam``'s one copy -- the OpenFOAM half of rule 2, never a
#: second variant (CLAUDE.md, "One reality").
_infer_unvalidated_value_kind = infer_unvalidated_value_kind


def _scanned(document: str, key_path: "tuple[str, ...]", value: Any) -> "tuple[str, bool]":
    """A key the catalogue lacks that the C++ reads at exactly this path
    (the shared OpenFOAM rule). A ``<solver>Coeffs`` first segment the
    catalogue's menu allows is spelled as the catalogue's own token."""
    from .cardiacfoam_plugin import CardiacFoamPlugin

    if document == _ELECTRO_DOCUMENT and len(key_path) > 1 and key_path[0] in _myocardium_solver_coeffs_names():
        key_path = (_COEFFS_TOKEN,) + tuple(key_path[1:])
    entries = (_ELECTRO_ENTRIES_BY_PATH if document == _ELECTRO_DOCUMENT else _PHYSICS_ENTRIES_BY_PATH).values()
    return scanned_key(
        document, tuple(key_path), value, mapping=CardiacFoamPlugin.get_profile().cxx_mapping, entries=entries,
    )


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
        if match is None and isinstance(value, Mapping) and _declares_members(document, key_path):
            # A whole map at a key whose members the catalog declares as a
            # dynamic ``<name>`` segment (``bathPotentialDomain.groundPatches
            # .<patch>``): each member is checked as that entry, and the map
            # is written whole, replacing the sub-dictionary (the writer
            # replaces rather than merges, logged as BB4 in
            # docs/solver-learning/cardiacfoam.md).
            for member, member_value in value.items():
                record_key_validator(document, key_path + (str(member),), member_value)
            return "mapping", True
        if match is None:
            try:
                return _scanned(document, key_path, value)
            except KeyError as exc:
                catalog_name = "electroProperties" if document == _ELECTRO_DOCUMENT else "physicsProperties"
                raise KeyError(
                    f"{document}:{dotted} is not declared by the {catalog_name} key catalog, and "
                    f"{exc.args[0]} (omnidriver catalog --uncatalogued lists what it reads)"
                ) from None
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


def record_key_catalog(case_root: Path) -> tuple[dict[str, Any], ...]:
    """Every key ``record_key_validator`` accepts for the case at
    ``case_root``, in ``runtime.record_surface``'s grammar (module
    docstring, "The catalogue").

    The electroProperties location is ``physics_layout.json``'s: a
    region-split case keeps it under ``constant/<region>/``, which the
    validator does not address, so that case is refused by name rather than
    catalogued with keys the validator would refuse. The case's
    ``myocardiumSolver`` must be one the catalogue's own vocabulary allows
    (``_myocardium_solver_coeffs_names``), for the same reason.
    """
    case_root = Path(case_root)
    region = region_of(case_root, "electro")
    if region is not None:
        raise PhysicsLayoutError(
            f"case {case_root} keeps its electro documents under constant/{region}/ "
            f"(physics_layout.json), but record keys are validated in {_ELECTRO_DOCUMENT!r} "
            "only; a region-split record needs record_key_validator to address its region first"
        )
    entries: list[dict[str, Any]] = []
    electro = case_root / _ELECTRO_DOCUMENT
    if electro.is_file():
        coeffs = f"{detect_myocardium_solver_name(electro)}Coeffs"
        if coeffs not in _myocardium_solver_coeffs_names():
            raise KeyError(
                f"{electro} names myocardiumSolver {coeffs[:-len('Coeffs')]!r}, which the "
                "electroProperties catalog's myocardiumSolver enum does not list"
            )
        entries += [
            listed_entry(_ELECTRO_DOCUMENT, entry.driver_path.replace(_COEFFS_TOKEN, coeffs, 1), entry)
            for entry in _ELECTRO_ENTRIES_BY_PATH.values()
        ]
    if (case_root / _PHYSICS_DOCUMENT).is_file():
        entries += [listed_entry(_PHYSICS_DOCUMENT, path, entry) for path, entry in _PHYSICS_ENTRIES_BY_PATH.items()]
    system = case_root / "system"
    entries += [
        {"document": path.relative_to(case_root).as_posix(), "key": ANY_KEY, "validated": False}
        for path in sorted(system.rglob("*")) if path.is_file()
    ]
    return tuple(entries)
