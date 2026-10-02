"""OpenFOAM half of a tutorial-record key validator, shared by every
OpenFOAM-based plugin (see CLAUDE.md "One reality"): an OpenFOAM-owned key
is written as asked, tagged by an inferred shape, and a key the catalogue
lacks is accepted when the plugin's own C++ reads it (``scanned_key``).
"""

from __future__ import annotations

import os
from typing import Any, Iterable

from omnidriver.core.contracts.catalogue_paths import catalogued_paths
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
    document: str, key_path: "tuple[str, ...]", value: Any, *, mapping: Any, entries: Iterable[Any],
) -> "tuple[str, bool] | None":
    """``(value_kind, validated)`` for a key ``document``'s catalogue
    (``entries``) lacks but the plugin's supplied C++ reads at a compatible
    scope: an ``uncatalogued`` key a study may set, validated by the scanned
    C++ type. ``None`` when the source is not supplied, the catalogue lists
    the key's name at another path (the catalogue says where it lives), or
    no read matches. Raises ``ValueError`` when the value does not fit the
    scanned type."""
    from .dict_keys_scanner import _PROBES, _path_matches, cached_scan, value_kind_of

    root = mapping.source_root(os.environ) if mapping is not None else None
    if root is None or not root.is_dir():
        return None
    if any(path.split(".")[-1] == key_path[-1] for path in catalogued_paths(tuple(entries))):
        return None
    name = document.rsplit("/", 1)[-1]
    reads = [
        read for read in cached_scan(root, cache_root=None).reads
        if read.key == key_path[-1] and read.scope is not None and not read.subdict
        and read.method not in _PROBES and _path_matches(read.scope + (read.key,), key_path)
        and (not read.root.startswith("document:") or read.root == f"document:{name}")
    ]
    if not reads:
        return None
    kinds = {value_kind_of(read.type) for read in reads} - {None}
    if len(kinds) != 1:
        return infer_unvalidated_value_kind(value), False
    (kind,) = kinds
    reasons = validate_value_shape(kind, value)
    if reasons:
        raise ValueError(
            f"{document}:{'.'.join(key_path)} is uncatalogued; the C++ reads it as "
            f"{reads[0].type} ({reads[0].file}:{reads[0].line}): {'; '.join(reasons)}"
        )
    return kind, True
