"""The OpenFOAM half of a tutorial-record key validator, shared by every
OpenFOAM-based solver plugin (CLAUDE.md, "One reality": "cardiacFOAM and
cardiacCore are both OpenFOAM-based, so they do every shared job the same
way... The shared mechanism lives in omnidriver-openfoam, never as two
variants").

A document under ``system/`` this package has no keyed catalog for is
written/compared as asked, with no catalog opinion on whether it is a real
key the C++ reads -- only a best-effort, purely descriptive Python-level
shape (``infer_unvalidated_value_kind``), so the case-value comparator
downstream has something typed to work with. Extracted 2026-09-28 (step S)
from ``omnidriver-cardiacfoam``'s ``record_key_validation
._infer_unvalidated_value_kind``, which cardiacCore's own validator now
shares rather than reimplementing.
"""

from __future__ import annotations

from typing import Any


def infer_unvalidated_value_kind(value: Any) -> str:
    """The best-effort, purely descriptive shape tag for an OpenFOAM-owned
    key no plugin catalogs. Never checked against anything -- there is no
    catalog to check it against.

    ``bool`` is checked before ``int`` because ``bool`` is an ``int``
    subclass in Python.
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
