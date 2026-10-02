"""The catalogue's conditional logic, run over one resolved dictionary.

A ``DictEntry`` states when it applies (``applicable_when``), when it is
required (``required``, ``required_when``), and what it forbids, excludes or
needs beside it (``forbidden_when``, ``mutually_exclusive_with``,
``co_required_with``). :func:`rule_diagnostics` reads those relations against
the values a case holds, once per concrete instance for an entry under a
``<name>`` block, and names every violated one. Menus and value types are not
judged here: the C++ owns them, and the scan reports what the catalogue lacks.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.specs.validation import slot_key

_PLACEHOLDER = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")
_SWITCH = {
    "true": True, "yes": True, "on": True, "y": True, "t": True,
    "false": False, "no": False, "off": False, "n": False, "f": False,
}


def flatten(node: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Every leaf of a parsed dictionary, keyed by its dotted path. Walks
    ``keys()``: foamlib's ``items()`` on a file also yields its header and
    every nested entry again."""
    leaves: dict[str, Any] = {}
    for name in node.keys():
        if name is None:
            continue
        value = node[name]
        if hasattr(value, "keys"):
            leaves.update(flatten(value, f"{prefix}{name}."))
        else:
            leaves[f"{prefix}{name}"] = value
    return leaves


def read_leaves(path: Path, scope: tuple[str, ...] = ()) -> dict[str, Any]:
    """The leaves of the dictionary at ``path``, or of its ``scope`` block."""
    from foamlib import FoamFile

    node: Any = FoamFile(path)
    for segment in scope:
        node = node[segment]
    return flatten(node)


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and value == "")


def _word(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _matches(actual: Any, expected: str | bool | tuple) -> bool:
    options = expected if isinstance(expected, tuple) else (expected,)
    actual = _word(actual)
    if isinstance(actual, bool):
        return any(_SWITCH.get(str(_word(option)).lower()) is actual for option in options)
    return actual in tuple(_word(option) for option in options)


def _format(predicate: Mapping[str, Any]) -> str:
    return " and ".join(
        f"{key} in ({', '.join(value)})" if isinstance(value, tuple) else f"{key}={value}"
        for key, value in predicate.items()
    )


def _instances(prefix: str, reserved: set[str], context: Mapping[str, Any]) -> list[str]:
    """Names with at least one leaf below them under ``prefix`` that no
    catalogued template spells literally (``ecgDomains.electrodePositions``
    is not an ECG domain called ``electrodePositions``)."""
    names = set()
    for key in context:
        if key.startswith(prefix):
            name, _dot, rest = key[len(prefix):].partition(".")
            if rest and name not in reserved:
                names.add(name)
    return sorted(names)


class _Instance:
    """One entry bound to one concrete instance name of its ``<name>`` block
    (or to none, for an entry outside any block)."""

    def __init__(self, context: Mapping[str, Any], template: str | None = None, name: str | None = None):
        self.context = context
        self.template = template
        self.bound = None if template is None else _PLACEHOLDER.sub(name, template, count=1)

    def resolve(self, path: str) -> str:
        key = slot_key(path)
        if self.template is not None and key.startswith(self.template):
            return self.bound + key[len(self.template):]
        return key

    def holds(self, path: str, expected: Any) -> bool:
        key = self.resolve(path)
        if not _PLACEHOLDER.search(key):
            return key in self.context and _matches(self.context[key], expected)
        pattern = re.compile(_PLACEHOLDER.sub("[^.]+", re.escape(key)))
        return any(
            pattern.fullmatch(name) and _present(value) and _matches(value, expected)
            for name, value in self.context.items()
        )

    def is_set(self, path: str) -> bool:
        key = self.resolve(path)
        return _present(self.context.get(key)) or any(name.startswith(key + ".") for name in self.context)


def rule_diagnostics(
    entries: Iterable[Any], context: Mapping[str, Any], *, document: str,
) -> list[StrictDiagnostic]:
    """Every catalogue relation ``context`` (a dictionary's leaves, keyed by
    dotted path below the catalogue's scope token) violates."""
    entries = tuple(entries)
    templates = {
        key[: match.end()]
        for entry in entries if entry.dynamic_path
        for key in (slot_key(entry.driver_path),)
        for match in (_PLACEHOLDER.search(key),) if match
    }
    found: list[StrictDiagnostic] = []

    def violated(field: str, message: str) -> None:
        found.append(diagnostic("error", "catalog_rule", message, source=document, field=field))

    for entry in entries:
        key = slot_key(entry.driver_path)
        match = _PLACEHOLDER.search(key) if entry.dynamic_path else None
        if match is None:
            bound = [_Instance(context)]
        else:
            prefix = key[: match.start()]
            reserved = {
                segment for template in templates if template.startswith(prefix)
                for segment in (template[len(prefix):].split(".")[0],)
                if not _PLACEHOLDER.fullmatch(segment)
            }
            bound = [
                _Instance(context, key[: match.end()], name)
                for name in _instances(prefix, reserved, context)
            ]
        for instance in bound:
            concrete = instance.resolve(entry.driver_path)
            if _PLACEHOLDER.search(concrete):
                continue
            set_here = instance.is_set(entry.driver_path)
            forbidden = {k: v for k, v in entry.forbidden_when.items() if instance.holds(k, v)}
            if set_here and forbidden:
                violated(concrete, f"{concrete} is forbidden when {_format(forbidden)}.")
            if forbidden or not all(instance.holds(k, v) for k, v in entry.applicable_when.items()):
                continue
            required = (
                any(instance.holds(k, v) for k, v in entry.required_when.items())
                if entry.required_when else entry.required
            )
            if required and not set_here:
                condition = f" when {_format(entry.required_when)}" if entry.required_when else ""
                violated(concrete, f"{concrete} is required{condition}.")
            if not set_here:
                continue
            for sibling in entry.mutually_exclusive_with:
                if instance.is_set(sibling):
                    violated(concrete, f"{concrete} is mutually exclusive with {instance.resolve(sibling)}.")
            for sibling in entry.co_required_with:
                if not instance.is_set(sibling):
                    violated(concrete, f"{concrete} requires {instance.resolve(sibling)} to be set as well.")
    return found
