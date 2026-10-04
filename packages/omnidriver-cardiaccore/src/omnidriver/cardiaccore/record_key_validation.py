"""cardiacCore's tutorial-record key catalogue and validator, on ``omnidriver-openfoam``'s shared :func:`make_validator`.
Documents are the ``system/<utility>Dict`` entries of ``catalogs/inputs.py``; a key the catalogue lacks is accepted when the C++ reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.runtime.record_surface import key_pattern
from omnidriver.openfoam.control_dict import CONTROL_DICT_DOCUMENT, control_dict_document, control_dict_listing
from omnidriver.openfoam.record_key_validation import (
    CataloguedDocument, listed_entry, make_validator, narrow_to_selectors, open_system_documents,
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
        for key, entry in by_key.items():
            if key_pattern(key).fullmatch(dotted):
                return entry, {}
        return None

    return CataloguedDocument(
        label="cardiacCore", entries=by_key.values, match=match, scan=lambda key_path: (token, *key_path),
    )


def _cardiaccore_mapping() -> Any:
    from .plugin import CardiacCorePlugin

    return CardiacCorePlugin.get_profile().cxx_mapping


record_key_validator = make_validator(
    {**{document: _document(by_key) for document, by_key in _ENTRIES_BY_DOCUMENT.items()}, CONTROL_DICT_DOCUMENT: control_dict_document()},
    mapping=_cardiaccore_mapping,
    owner="cardiacCore",
)


def record_key_catalog(case_root: Path) -> "tuple[dict[str, Any], ...]":
    """Every key ``record_key_validator`` accepts for the case at ``case_root``."""
    return (
        *(
            listed_entry(document, key, entry)
            for document, by_key in _ENTRIES_BY_DOCUMENT.items()
            for key, entry in by_key.items()
        ),
        *control_dict_listing(case_root),
        *open_system_documents(case_root, exclude=_ENTRIES_BY_DOCUMENT),
    )


#: cardiacCore's records fix no selector their keys depend on.
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
