"""A case.json document: read a dotted key, patch dotted keys, compare values."""
from __future__ import annotations

import json
from typing import Any


class CaseJsonError(ValueError):
    """A case.json that cannot be read or patched as asked."""


def _load(text: str) -> dict[str, Any]:
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise CaseJsonError(f"case.json is not JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise CaseJsonError("case.json is not a JSON object")
    return document


def read_value(text: str, key: str) -> Any | None:
    """The value at dotted ``key``, or ``None`` when the document lacks it."""
    node: Any = _load(text)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def patch(text: str, values: dict[str, Any]) -> str:
    """The document with each dotted key set. A field may be added to an
    existing object, never a top-level key the document lacks, and a list
    element is not addressable."""
    document = _load(text)
    for key, value in values.items():
        *parents, leaf = key.split(".")
        if parents and parents[0] not in document or not parents and leaf not in document:
            raise CaseJsonError(f"{key}: case.json has no {(parents or [leaf])[0]!r}, and a patch adds no top-level key")
        node = document
        for part in parents:
            node = node.get(part) if isinstance(node, dict) else None
            if not isinstance(node, dict):
                raise CaseJsonError(f"{key}: {part!r} is not an object; a list element or scalar has no fields to set")
        node[leaf] = value
    return json.dumps(document, indent=2) + "\n"


def values_agree(value_kind: str, requested: Any, current: Any) -> bool:
    del value_kind
    numbers = (int, float)
    if isinstance(requested, bool) or isinstance(current, bool):
        return type(requested) is type(current) and requested == current
    if isinstance(requested, numbers) and isinstance(current, numbers):
        return float(requested) == float(current)
    return requested == current
