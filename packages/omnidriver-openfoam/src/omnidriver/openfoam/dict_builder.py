"""Solver-neutral primitives for synthesising OpenFOAM dictionary text: entry
selection, value resolution, and block serialisation. Solver-specific
builders live in the owning plugin, and judge what they build with
``case_rules``.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from omnidriver.core.contracts.catalogue_paths import PLACEHOLDER, slot_key

from .case_rules import applicable_entries

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry


def select_applicable_entries(
    context: dict[str, Any],
    *,
    entries: list[DictEntry],
) -> list[DictEntry]:
    """Return entries whose `applicable_when` predicate matches `context` and
    whose `forbidden_when` predicate does not. `entries` is always supplied
    by the caller; this module knows no solver's catalog."""
    return applicable_entries(entries, context)


def populate_values(
    entries: list[DictEntry],
    context: dict[str, Any],
    *,
    typical_value_fallback: bool = True,
) -> dict[str, str]:
    """Resolve each entry's value to write: an explicit value in `context`,
    else `entry.typical_value` when `typical_value_fallback`, else omitted
    (left for the caller's rule check to flag if required)."""
    populated: dict[str, str] = {}

    dynamic_entries = []
    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            # Any <placeholder> segment is a wildcard, not a fixed set of names --
            # a template can use any placeholder name and must still match.
            pattern = PLACEHOLDER.sub(r"([^.]+)", re.escape(template))
            dynamic_entries.append((entry, template, re.compile(f"^{pattern}$")))

    active_instances: dict[str, set[tuple[str, ...]]] = {}
    for key, val in context.items():
        if val in (None, ""):
            continue
        for entry, template, regex in dynamic_entries:
            match = regex.match(key)
            if match:
                groups = match.groups()
                prefix = template.split(".<")[0]
                active_instances.setdefault(prefix, set()).add(groups)

    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            prefix = template.split(".<")[0]
            if prefix in active_instances:
                for groups in active_instances[prefix]:
                    concrete_key = template
                    for captured in groups:
                        concrete_key = PLACEHOLDER.sub(captured, concrete_key, count=1)

                    if concrete_key in context and context[concrete_key] not in (None, ""):
                        populated[concrete_key] = str(context[concrete_key])
                    elif typical_value_fallback and entry.typical_value:
                        populated[concrete_key] = entry.typical_value
            continue

        key = slot_key(entry.driver_path)
        if key in context and context[key] not in (None, ""):
            populated[key] = str(context[key])
            continue
        if typical_value_fallback and entry.typical_value:
            conflict = False
            for mx_path in getattr(entry, "mutually_exclusive_with", ()):
                mx_key = slot_key(mx_path)
                if mx_key in context and context[mx_key] not in (None, ""):
                    conflict = True
                    break
            if not conflict:
                populated[key] = entry.typical_value
            continue
    return populated


def match_dynamic_entry(
    key: str, entries,
) -> "tuple[DictEntry, dict[str, str]] | None":
    """Match `key` against a `dynamic_path` entry's template, returning the
    entry and the concrete value each placeholder captured (or None). Same
    wildcard convention as the catalogue's ``<placeholder>`` segments.

    Returns the first match; the catalog has no two dynamic entries whose
    templates collide at the same segment length today.
    """
    normalized = slot_key(key)
    for entry in entries:
        if not getattr(entry, "dynamic_path", False):
            continue
        entry_key = slot_key(entry.driver_path)
        placeholders = PLACEHOLDER.findall(entry_key)
        pattern = PLACEHOLDER.sub(r"([^.]+)", re.escape(entry_key))
        match = re.fullmatch(pattern, normalized)
        if match:
            return entry, dict(zip(placeholders, match.groups()))
    return None


def _set_nested(node: dict, path: list[str], value: Any) -> None:
    """Insert `value` at `path` inside the nested dict `node`, creating
    intermediate sub-dicts as needed."""
    cursor = node
    for segment in path[:-1]:
        cursor = cursor.setdefault(segment, {})
        if not isinstance(cursor, dict):
            raise ValueError(
                f"Path collision in serialiser at segment {segment!r}: a leaf "
                f"value exists where a sub-block is needed."
            )
    cursor[path[-1]] = value


def _openfoam_value_token(value: str) -> str:
    # OpenFOAM's tokenizer reads a bare token starting with a digit as a number
    # (e.g. `3D` becomes label `3` plus junk), so only that case needs quoting.
    if not isinstance(value, str) or not value:
        return value
    token = value.strip()
    if not token or not token[0].isdigit():
        return value
    if any(ch.isspace() for ch in token) or token[0] in "([{\"":
        return value
    try:
        float(token)
    except ValueError:
        return f'"{token}"'
    return value


def _serialize_block(tree: dict, indent: int) -> str:
    """Emit nested OpenFOAM block syntax. Leaves are `key value;`,
    sub-blocks are `key\\n{\\n  ...\\n}` recursively."""
    lines: list[str] = []
    pad = " " * indent
    for key, value in tree.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}")
            lines.append(f"{pad}{{")
            lines.append(_serialize_block(value, indent + 4))
            lines.append(f"{pad}}}")
        else:
            lines.append(f"{pad}{key} {_openfoam_value_token(value)};")
    return "\n".join(lines)
