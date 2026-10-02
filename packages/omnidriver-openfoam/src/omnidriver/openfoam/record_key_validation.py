"""OpenFOAM half of a tutorial-record key validator, shared by every
OpenFOAM-based plugin (see CLAUDE.md "One reality"): an OpenFOAM-owned key
is written as asked, tagged by an inferred shape, and a key the catalogue
lacks is accepted when the plugin's own C++ reads it (``scanned_key``).
"""

from __future__ import annotations

import os
from typing import Any, Iterable

from omnidriver.core.contracts.dictionary import validate_value_shape


def infer_unvalidated_value_kind(value: Any) -> str:
    """Best-effort, purely descriptive shape tag for an OpenFOAM-owned key no
    plugin catalogs; never checked against anything.

    `bool` is checked before `int` because `bool` is an `int` subclass.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return "integer_list"
        return "scalar_list"
    if isinstance(value, str) and value.split() != [value]:
        return "string"
    return "word"


def listed_entry(document: str, key: str, entry: Any) -> dict[str, Any]:
    """One key-catalogue listing (`record_surface`'s grammar) for a
    catalogued `DictEntry`: what `describe` and `omnidriver catalog` show
    for it. The catalogues record no default, only a `typical_value`."""
    return {
        "document": document, "key": key, "driver_path": entry.driver_path,
        "value_kind": entry.value_kind, "unit": entry.unit,
        "description": entry.description, "menu": list(entry.enum_values),
        "typical_value": entry.typical_value,
        "applicable_when": {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in entry.applicable_when.items()
        },
        "source_refs": list(entry.source_refs),
    }


def scanned_key(
    document: str, catalog_path: "tuple[str, ...]", value: Any, *, mapping: Any, entries: Iterable[Any],
) -> "tuple[str, bool]":
    """``(value_kind, True)`` for a key the catalogue lacks that the
    plugin's supplied C++ reads at exactly ``catalog_path``: a read whose
    root ``dict_keys_scanner.locate`` places in ``document`` (catalogued by
    ``entries``) so that place, its scope and its key spell that path.
    ``catalog_path`` is in the catalogue's spelling (a ``$TOKEN`` first
    segment for a scoped block). Raises ``KeyError`` saying why when no read
    matches, and ``ValueError`` when the value does not fit the scanned
    type."""
    from .dict_keys_scanner import _segment_matches, cached_scan, locate, value_kind_of

    root = mapping.source_root(os.environ) if mapping is not None else None
    if root is None or not root.is_dir():
        variable = mapping.source_root_variable if mapping is not None else "the source root"
        raise KeyError(f"the C++ source is not supplied ({variable}), so no uncatalogued key can be checked")
    scan = cached_scan(root, cache_root=None)
    name = document.rsplit("/", 1)[-1]
    reads = [
        read for read in scan.reads
        if read.value_read and read.key == catalog_path[-1]
        and (not read.root.startswith("document:") or read.root == f"document:{name}")
    ]
    if not reads:
        raise KeyError(f"the supplied C++ reads no key named {catalog_path[-1]!r}")
    placed = locate(scan, entries, document=name)
    spelled = [
        (read, place + read.scope + (read.key,)) for read in reads for place in placed.get(read.root, ())
    ]
    matching = [
        read for read, path in spelled
        if len(path) == len(catalog_path) and all(_segment_matches(key, listed) for listed, key in zip(path, catalog_path))
    ]
    if not matching:
        if spelled:
            raise KeyError(
                f"the supplied C++ reads {catalog_path[-1]!r} at "
                f"{', '.join(sorted({'.'.join(path) for _read, path in spelled}))}, not at {'.'.join(catalog_path)}"
            )
        raise KeyError(
            f"the supplied C++ reads {catalog_path[-1]!r} only through dictionaries the scan cannot place ("
            + ", ".join(sorted({f"{read.file}:{read.line}" for read in reads})) + ")"
        )
    kinds = {value_kind_of(read.type) for read in matching} - {None}
    if len(kinds) != 1:
        return infer_unvalidated_value_kind(value), True
    (kind,) = kinds
    reasons = validate_value_shape(kind, value)
    if reasons:
        raise ValueError(
            f"this uncatalogued key is read by the C++ as "
            f"{matching[0].type} ({matching[0].file}:{matching[0].line}): {'; '.join(reasons)}"
        )
    return kind, True
