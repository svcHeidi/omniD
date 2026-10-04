"""cardiacFOAM's tutorial-record key catalogue and validator, on ``omnidriver-openfoam``'s shared validator (:func:`make_validator`).

Covers ``constant/electroProperties``, ``constant/physicsProperties``, ``constant/prePacingProperties`` and the keys of ``system/controlDict`` the catalogue lists (any other controlDict key is written as asked); ``record_key_catalog`` lists what is accepted for one case."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.openfoam.case_rules import match_dynamic_entry
from omnidriver.openfoam.control_dict import CONTROL_DICT_DOCUMENT, control_dict_document, control_dict_listing
from omnidriver.openfoam.record_key_validation import (
    CataloguedDocument, listed_entry, make_validator, open_system_documents,
)

from .common_dict_entries import PHYSICS_PROPERTY_ENTRIES, PRE_PACING_PROPERTY_ENTRIES
from .detection import detect_myocardium_solver_name
from .dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from .physics_layout import PhysicsLayoutError, region_of

ELECTRO_DOCUMENT = "constant/electroProperties"
PHYSICS_DOCUMENT = "constant/physicsProperties"
PRE_PACING_DOCUMENT = "constant/prePacingProperties"

#: The scope token every coeffs-scoped catalogue ``driver_path`` starts with.
_COEFFS_TOKEN = "$ELECTRO_MODEL_COEFFS"
_PRE_PACING_TOKEN = "$PRE_PACING"

_ELECTRO_ENTRIES_BY_PATH = {
    entry.driver_path: entry for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values() for entry in group
}
_PHYSICS_ENTRIES_BY_PATH = {entry.driver_path: entry for entry in PHYSICS_PROPERTY_ENTRIES}
_PRE_PACING_ENTRIES_BY_PATH = {entry.driver_path: entry for entry in PRE_PACING_PROPERTY_ENTRIES}


def _coeffs_names() -> "frozenset[str]":
    """Every ``<solver>Coeffs`` the catalogue's ``myocardiumSolver`` menu sanctions."""
    entry = _ELECTRO_ENTRIES_BY_PATH.get("myocardiumSolver")
    if entry is None or not entry.enum_values:
        raise AssertionError(
            "the electroProperties catalog declares no 'myocardiumSolver' menu to derive "
            "'<solver>Coeffs' names from: a catalog defect, not a normal refusal"
        )
    return frozenset(f"{value}Coeffs" for value in entry.enum_values)


def _tokenised(key_path: "tuple[str, ...]") -> "tuple[str, ...]":
    """``key_path`` with a legal ``<solver>Coeffs`` first segment spelled as the catalogue's token."""
    if len(key_path) > 1 and key_path[0] in _coeffs_names():
        return (_COEFFS_TOKEN, *key_path[1:])
    return key_path


def _electro_match(key_path: "tuple[str, ...]"):
    """The entry (and dynamic-path binding) a literal electroProperties key path addresses."""
    dotted = ".".join(key_path)
    entry = _ELECTRO_ENTRIES_BY_PATH.get(dotted)
    if entry is not None and not dotted.startswith(f"{_COEFFS_TOKEN}."):
        return entry, {}
    # A match through the token needs a legal <solver>Coeffs first segment: an
    # arbitrary one, or the token itself, must not stand in for it.
    if len(key_path) == 1 or key_path[0] not in _coeffs_names():
        return None
    templated = ".".join(_tokenised(key_path))
    entry = _ELECTRO_ENTRIES_BY_PATH.get(templated)
    if entry is not None:
        return entry, {}
    return match_dynamic_entry(templated, _ELECTRO_ENTRIES_BY_PATH.values())


def _electro_declares_members(key_path: "tuple[str, ...]") -> bool:
    parent = ".".join(_tokenised(key_path))
    return any(
        entry.dynamic_path and path.rpartition(".")[0] == parent and path.rpartition(".")[2].startswith("<")
        for path, entry in _ELECTRO_ENTRIES_BY_PATH.items()
    )


def _physics_match(key_path: "tuple[str, ...]"):
    entry = _PHYSICS_ENTRIES_BY_PATH.get(".".join(key_path))
    return None if entry is None else (entry, {})


def _pre_pacing_match(key_path: "tuple[str, ...]"):
    """The entry a ``prePacingProperties`` key path addresses, at the file's root or in one ``regions.<name>`` block."""
    templated = ".".join((_PRE_PACING_TOKEN, *key_path))
    entry = _PRE_PACING_ENTRIES_BY_PATH.get(templated)
    return (entry, {}) if entry is not None else match_dynamic_entry(templated, _PRE_PACING_ENTRIES_BY_PATH.values())


def _pre_pacing_declares_members(key_path: "tuple[str, ...]") -> bool:
    """A ``singleCellStimulus`` block, at the root or in a region, is the map of its catalogued keys."""
    return key_path[-1:] == ("singleCellStimulus",) and (len(key_path) == 1 or key_path[:1] == ("regions",) and len(key_path) == 3)


def cardiacfoam_mapping() -> Any:
    from .cardiacfoam_plugin import CardiacFoamPlugin

    return CardiacFoamPlugin.get_profile().cxx_mapping


record_key_validator = make_validator(
    {
        ELECTRO_DOCUMENT: CataloguedDocument(
            label="electroProperties",
            entries=_ELECTRO_ENTRIES_BY_PATH.values,
            match=_electro_match,
            scan=_tokenised,
            # A map whose members the catalogue declares as one dynamic <name>
            # segment is checked member by member and validates as "mapping";
            # the writer replaces the whole sub-dictionary with it.
            members=_electro_declares_members,
        ),
        PHYSICS_DOCUMENT: CataloguedDocument(
            label="physicsProperties",
            entries=_PHYSICS_ENTRIES_BY_PATH.values,
            match=_physics_match,
            scan=lambda key_path: key_path,
        ),
        PRE_PACING_DOCUMENT: CataloguedDocument(
            label="prePacingProperties",
            entries=_PRE_PACING_ENTRIES_BY_PATH.values,
            match=_pre_pacing_match,
            scan=lambda key_path: (_PRE_PACING_TOKEN, *key_path),
            members=_pre_pacing_declares_members,
        ),
        CONTROL_DICT_DOCUMENT: control_dict_document(),
    },
    mapping=cardiacfoam_mapping,
    owner="cardiacFOAM",
)


def record_key_catalog(case_root: Path) -> tuple[dict[str, Any], ...]:
    """Every key ``record_key_validator`` accepts for the case at ``case_root``.

    The electroProperties location is ``physics_layout.json``'s: a region-split
    case keeps it under ``constant/<region>/``, which the validator does not
    address, so that case is refused by name. The case's ``myocardiumSolver``
    must be one the catalogue's menu allows, for the same reason."""
    case_root = Path(case_root)
    region = region_of(case_root, "electro")
    if region is not None:
        raise PhysicsLayoutError(
            f"case {case_root} keeps its electro documents under constant/{region}/ "
            f"(physics_layout.json), but record keys are validated in {ELECTRO_DOCUMENT!r} "
            "only; a region-split record needs record_key_validator to address its region first"
        )
    entries: list[dict[str, Any]] = []
    electro = case_root / ELECTRO_DOCUMENT
    if electro.is_file():
        coeffs = f"{detect_myocardium_solver_name(electro)}Coeffs"
        if coeffs not in _coeffs_names():
            raise KeyError(
                f"{electro} names myocardiumSolver {coeffs[:-len('Coeffs')]!r}, which the "
                "electroProperties catalog's myocardiumSolver enum does not list"
            )
        entries += [
            listed_entry(ELECTRO_DOCUMENT, entry.driver_path.replace(_COEFFS_TOKEN, coeffs, 1), entry)
            for entry in _ELECTRO_ENTRIES_BY_PATH.values()
        ]
    if (case_root / PHYSICS_DOCUMENT).is_file():
        entries += [listed_entry(PHYSICS_DOCUMENT, path, entry) for path, entry in _PHYSICS_ENTRIES_BY_PATH.items()]
    if (case_root / PRE_PACING_DOCUMENT).is_file():
        entries += [
            listed_entry(PRE_PACING_DOCUMENT, path.removeprefix(f"{_PRE_PACING_TOKEN}."), entry)
            for path, entry in _PRE_PACING_ENTRIES_BY_PATH.items()
        ]
    return (*entries, *control_dict_listing(case_root), *open_system_documents(case_root))
