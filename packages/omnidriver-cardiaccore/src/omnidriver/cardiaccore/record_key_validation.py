"""cardiacCore's tutorial-record key validator and catalog.

**One reality** (CLAUDE.md): an uncatalogued ``system/`` document falls back
to the same rule ``omnidriver-cardiacfoam``'s validator uses, shared through
``omnidriver-openfoam`` rather than reimplemented. cardiacCore adds only its
own half: the utility dicts ``catalogs/inputs.py`` catalogues, with evidence
from the native C++ source for each Dict.

Three outcomes, the same three cardiacFOAM's validator has:

1. A key one of ``catalogs/inputs.py``'s ``DictEntry`` tuples declares for
   that document (matched against the entry's own ``driver_path`` suffix, in
   ``record_surface``'s key grammar) -- checked against the entry's
   ``value_kind`` via ``validate_value_shape``, ``validated=True``; or a key
   the catalogue lacks that the supplied C++ reads, checked against the
   scanned type (``omnidriver.openfoam.record_key_validation.scanned_key``).
2. Any other ``system/`` document (``controlDict``, ``fvSchemes``,
   ``fvSolution`` -- this package catalogues none of them) -- accepted,
   ``validated=False``, its shape inferred by the shared OpenFOAM function.
3. Anything else -- refused BY NAME.

cardiacCore declares no ``constant/*`` catalogued document of its own (unlike
cardiacFOAM's ``electroProperties``/``physicsProperties``): its utilities
read/write ``0/*`` fields directly, never through a study key, so a
document:key study only ever targets a ``system/*Dict``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.runtime.record_surface import ANY_KEY
from omnidriver.openfoam.record_key_validation import infer_unvalidated_value_kind, listed_entry, scanned_key

from .catalogs.inputs import CATALOG


def _suffix(driver_path: str) -> str:
    """``driver_path`` past its ``$TOKEN.`` scope prefix -- the key relative
    to the document ``CATALOG.documents`` already groups it under."""
    _token, _dot, rest = driver_path.partition(".")
    return rest


#: ``{"system/setCardiacConductivityDict": {"df": DictEntry(...), ...}, ...}``
#: -- every catalogued utility dict, keyed by its concrete ``system/`` path,
#: each entry keyed by its own suffix (``record_surface``'s key grammar: a
#: literal segment, or ``<name>``/``[Int]`` where the catalog already
#: declares one).
_ENTRIES_BY_DOCUMENT: dict[str, dict[str, Any]] = {
    f"system/{name}": {_suffix(entry.driver_path): entry for entry in entries}
    for name, entries in CATALOG.documents.items()
}


def _match(document: str, key_path: "tuple[str, ...]"):
    from omnidriver.core.runtime.record_surface import key_pattern

    by_key = _ENTRIES_BY_DOCUMENT.get(document)
    if by_key is None:
        return None
    dotted = ".".join(key_path)
    for key, entry in by_key.items():
        if key_pattern(key).fullmatch(dotted):
            return entry
    return None


def record_key_validator(document: str, key_path: "tuple[str, ...]", value: Any) -> "tuple[str, bool]":
    """The one callable ``RecordKeyValidationCapability.validator()`` returns
    for a cardiacCore stack. See the module docstring for the three rules
    this implements.

    A catalogued document's own unmatched key is refused (rule 3), not
    accepted unvalidated (rule 2): a document in ``_ENTRIES_BY_DOCUMENT`` has
    a real catalog, so an undeclared key (e.g. a typo) is a catalog miss, not
    an OpenFOAM-owned key this package simply declares no catalog for at all
    (``controlDict``, ``fvSchemes``, ``fvSolution``,
    ``coordinatesConventionDict``)."""
    dotted = ".".join(key_path)
    if document in _ENTRIES_BY_DOCUMENT:
        entry = _match(document, key_path)
        if entry is None:
            from .plugin import CardiacCorePlugin

            scanned = scanned_key(
                document, key_path, value, mapping=CardiacCorePlugin.get_profile().cxx_mapping,
                entries=_ENTRIES_BY_DOCUMENT[document].values(),
            )
            if scanned is not None:
                return scanned
            raise KeyError(
                f"{document}:{dotted} is not declared by its cardiacCore key catalog, and "
                "the supplied C++ source reads no such key (omnidriver catalog "
                "--uncatalogued lists what it reads)"
            )
        reasons = validate_value_shape(entry.value_kind, value)
        if reasons:
            raise ValueError(
                f"{document}:{dotted} does not fit catalogued value_kind "
                f"{entry.value_kind!r}: {'; '.join(reasons)}"
            )
        return entry.value_kind, True
    if document.startswith("system/"):
        return infer_unvalidated_value_kind(value), False
    raise KeyError(
        f"{document}:{dotted} is neither a cardiacCore-catalogued utility "
        "dict key nor a 'system/' OpenFOAM document; refusing rather than "
        "silently treating an unrecognised document as an unvalidated key"
    )


def record_key_catalog(case_root: Path) -> "tuple[dict[str, Any], ...]":
    """Every key ``record_key_validator`` accepts for the case at
    ``case_root``, in ``record_surface``'s grammar."""
    case_root = Path(case_root)
    entries: list[dict[str, Any]] = [
        listed_entry(document, key, entry)
        for document, by_key in _ENTRIES_BY_DOCUMENT.items()
        for key, entry in by_key.items()
    ]
    system = case_root / "system"
    if system.is_dir():
        entries += [
            {"document": path.relative_to(case_root).as_posix(), "key": ANY_KEY, "validated": False}
            for path in sorted(system.rglob("*"))
            if path.is_file() and path.relative_to(case_root).as_posix() not in _ENTRIES_BY_DOCUMENT
        ]
    return tuple(entries)
