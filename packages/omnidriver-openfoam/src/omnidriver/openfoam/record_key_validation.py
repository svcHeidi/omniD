"""OpenFOAM half of a tutorial-record key validator, shared by every
OpenFOAM-based plugin (see CLAUDE.md "One reality"). An uncatalogued key is
written/compared as asked, tagged only by a best-effort inferred shape.
"""

from __future__ import annotations

from typing import Any


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
