"""cardiacSubstrateFOAM's tutorial-record key catalogue and validator, on ``omnidriver-openfoam``'s shared :func:`make_validator`.
Documents are the ``system/<utility>Dict`` entries of ``catalogs/inputs.py``; a key the catalogue lacks is accepted when the C++ reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.openfoam.case_rules import match_dynamic_entry
from omnidriver.openfoam.record_key_validation import (
    CataloguedDocument, listed_entry, make_validator, narrow_to_selectors,
)

from .catalogs.inputs import CATALOG


def _suffix(driver_path: str) -> str:
    """``driver_path`` past its ``$TOKEN.`` scope prefix."""
    return driver_path.partition(".")[2]


#: ``{"system/setCardiacConductivityDict": {"df": DictEntry(...), ...}, ...}``,
#: each entry keyed by its own suffix.
_ENTRIES_BY_DOCUMENT: dict[str, dict[str, Any]] = {
    f"system/{name}": {_suffix(entry.driver_path): entry for entry in entries}
    for name, entries in CATALOG.documents.items()
}


def _document(by_key: dict[str, Any]) -> CataloguedDocument:
    token = next(iter(by_key.values())).driver_path.partition(".")[0]

    def match(key_path: "tuple[str, ...]"):
        dotted = ".".join(key_path)
        entry = by_key.get(dotted)
        return (entry, {}) if entry is not None else match_dynamic_entry(dotted, by_key.values())

    return CataloguedDocument(
        label="cardiacSubstrateFOAM", entries=by_key.values, match=match, scan=lambda key_path: (token, *key_path),
    )


def _cardiacsubstrate_mapping() -> Any:
    from .plugin import CardiacSubstratePlugin

    return CardiacSubstratePlugin.get_profile().cxx_mapping


record_key_validator = make_validator(
    {document: _document(by_key) for document, by_key in _ENTRIES_BY_DOCUMENT.items()},
    mapping=_cardiacsubstrate_mapping,
    owner="cardiacSubstrateFOAM",
)


def record_key_catalog(case_root: Path) -> "tuple[dict[str, Any], ...]":
    """Every utility-dictionary key ``record_key_validator`` accepts; the OpenFOAM layer lists the rest."""
    del case_root
    return tuple(
        listed_entry(document, key, entry)
        for document, by_key in _ENTRIES_BY_DOCUMENT.items()
        for key, entry in by_key.items()
    )


#: cardiacSubstrateFOAM's records fix no selector their keys depend on.
RECORD_SELECTORS: "dict[str, tuple[str, ...]]" = {}


def applicable_record_keys(keys: "tuple[dict[str, Any], ...]", case_root: Path) -> "tuple[dict[str, Any], ...]":
    """``keys`` less those the case's selectors rule out (none are named)."""
    return narrow_to_selectors(
        keys, case_root, selectors=RECORD_SELECTORS,
        entries={
            document: {entry.driver_path: entry for entry in by_key.values()}
            for document, by_key in _ENTRIES_BY_DOCUMENT.items()
        },
    )
