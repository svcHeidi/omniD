"""The one evaluator of a catalogue's conditional logic and of the keys the
solver's C++ requires, run over one resolved dictionary.

A ``DictEntry`` states when it applies (``applicable_when``), when it is
required (``required``, ``required_when``), and what it forbids, excludes or
needs beside it (``forbidden_when``, ``mutually_exclusive_with``,
``co_required_with``). :func:`rule_diagnostics` reads those relations against
the values a case holds, once per concrete instance for an entry under a
``<name>`` block, and names every violated one. The same pass names a key the
supplied C++ reads without a default that the catalogue lacks and the case
does not set. Menus and value types are not judged here: the C++ owns them.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.catalogue_paths import PLACEHOLDER, slot_key
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

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
        self.bound = None if template is None else PLACEHOLDER.sub(name, template, count=1)

    def resolve(self, path: str) -> str:
        key = slot_key(path)
        if self.template is not None and key.startswith(self.template):
            return self.bound + key[len(self.template):]
        return key

    def holds(self, path: str, expected: Any) -> bool:
        key = self.resolve(path)
        if not PLACEHOLDER.search(key):
            return key in self.context and _matches(self.context[key], expected)
        pattern = re.compile(PLACEHOLDER.sub("[^.]+", re.escape(key)))
        return any(
            pattern.fullmatch(name) and _present(value) and _matches(value, expected)
            for name, value in self.context.items()
        )

    def is_set(self, path: str) -> bool:
        key = self.resolve(path)
        return _present(self.context.get(key)) or any(name.startswith(key + ".") for name in self.context)

    def forbidden_by(self, entry: Any) -> dict[str, Any]:
        return {k: v for k, v in entry.forbidden_when.items() if self.holds(k, v)}

    def applies(self, entry: Any) -> bool:
        return not self.forbidden_by(entry) and all(self.holds(k, v) for k, v in entry.applicable_when.items())

    def requires(self, entry: Any) -> bool:
        if entry.required_when:
            return any(self.holds(k, v) for k, v in entry.required_when.items())
        return entry.required


def applicable_entries(entries: Iterable[Any], context: Mapping[str, Any]) -> list[Any]:
    """The entries whose ``applicable_when`` holds in ``context`` and whose
    ``forbidden_when`` does not."""
    instance = _Instance(context)
    return [entry for entry in entries if instance.applies(entry)]


def forbidden_in(entries: Iterable[Any], context: Mapping[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    """Each entry ``context`` sets that its own ``forbidden_when`` forbids,
    with the predicates that hold."""
    instance = _Instance(context)
    return [(entry, forbidden) for entry in entries if instance.is_set(entry.driver_path) and (forbidden := instance.forbidden_by(entry))]


def _scan_facts(mapping: Any, entries: tuple[Any, ...], document: str):
    """What the supplied C++ adds to the catalogue's rules: the keys it
    requires that ``entries`` lack, the classes that build them, and the names
    its selection tables register for each enum. Nothing when the source is
    not supplied."""
    from .dict_keys_scanner import (
        built_when, cached_scan, registered_menus, required_reads, scan_cache_root, unread_entries,
    )

    root = mapping.source_root(os.environ) if mapping is not None else None
    if root is None or not root.is_dir():
        return {}, {}, {}, set()
    scan = cached_scan(root, cache_root=scan_cache_root())
    reviewed = json.loads(Path(mapping.allowlist_path).read_text())
    return (
        required_reads(scan, entries, document=document.rsplit("/", 1)[-1]),
        registered_menus(reviewed, scan, entries),
        built_when(reviewed, scan),
        {entry.driver_path for entry in unread_entries(scan, entries, reviewed)},
    )


def _scan_requirement(
    path: tuple[str, ...], reads: list[Any], context: Mapping[str, Any], document: str,
    built: Mapping[str, frozenset[str]],
) -> list[StrictDiagnostic]:
    """A key the C++ requires, absent from the case, in each block of the
    case that a class the case builds reads it from. A class is built when a
    selection table registers it under a name the case selects, or when the
    scan or the plugin's reviewed ``built_when`` ties it to a selector value
    the case holds. A class nothing ties to the case is noted, not judged."""
    from .dict_keys_scanner import owner_of

    selected = {str(_word(value)) for value in context.values()}

    def ties(read: Any) -> frozenset[str] | None:
        if read.selected_as:
            return frozenset(name for _base, name in read.selected_as)
        return built.get(owner_of(read))

    judged = [read for read in reads if (names := ties(read)) is not None and names & selected]
    unjudged = [read for read in reads if ties(read) is None]
    segments = path[1:] if path[0].startswith("$") else path
    block, key = segments[:-1], segments[-1]
    pattern = re.compile(r"\.".join(r"[^.]+" if PLACEHOLDER.fullmatch(s) or s == "*" else re.escape(s) for s in block))
    blocks = sorted({
        ".".join(name.split(".")[:len(block)]) for name in context
        if len(name.split(".")) > len(block) and pattern.fullmatch(".".join(name.split(".")[:len(block)]))
    }) if block else [""]
    found = []
    for scope in blocks:
        concrete = f"{scope}.{key}" if scope else key
        if _present(context.get(concrete)) or any(name.startswith(concrete + ".") for name in context):
            continue
        for level, code, group, how in (
            ("error", "cxx_required_key", judged, "this case builds the class that reads it"),
            ("info", "cxx_required_key_unjudged", unjudged, "the scan cannot tell whether this case builds the class that reads it"),
        ):
            if not group:
                continue
            sources = ", ".join(sorted({f"{read.file}:{read.line} ({read.function})" for read in group}))
            found.append(diagnostic(
                level, code,
                f"{concrete} is read as {group[0].method}<{group[0].type or 'an unresolved type'}> with no default at "
                f"{sources}, and the catalogue does not list it (omnidriver catalog --uncatalogued describes it); "
                + (f"{how}, so set {concrete} in {document}"
                   if level == "error" else f"{how}; if it does, set {concrete} in {document}")
                + (f" (below {path[0]})" if path[0].startswith("$") else "") + ".",
                source=document, field=concrete,
            ))
    return found


def rule_diagnostics(
    entries: Iterable[Any], context: Mapping[str, Any], *, document: str, mapping: Any = None,
) -> list[StrictDiagnostic]:
    """Every catalogue relation ``context`` (a dictionary's leaves, keyed by
    dotted path below the catalogue's scope token) violates, each enum value
    outside its menu and, when the plugin's ``mapping`` supplies its C++
    source, each key that C++ requires and ``context`` lacks. A menu is the names
    the C++ registers for the enum when its source is supplied and maps it to a
    selection table, the catalogue's otherwise."""
    entries = tuple(entries)
    requirements, registered, built, unread = _scan_facts(mapping, entries, document)
    templates = {
        key[: match.end()]
        for entry in entries if entry.dynamic_path
        for key in (slot_key(entry.driver_path),)
        for match in (PLACEHOLDER.search(key),) if match
    }
    found: list[StrictDiagnostic] = []

    def violated(field: str, message: str) -> None:
        found.append(diagnostic("error", "catalog_rule", message, source=document, field=field))

    for entry in entries:
        key = slot_key(entry.driver_path)
        match = PLACEHOLDER.search(key) if entry.dynamic_path else None
        if match is None:
            bound = [_Instance(context)]
        else:
            prefix = key[: match.start()]
            reserved = {
                segment for template in templates if template.startswith(prefix)
                for segment in (template[len(prefix):].split(".")[0],)
                if not PLACEHOLDER.fullmatch(segment)
            }
            bound = [
                _Instance(context, key[: match.end()], name)
                for name in _instances(prefix, reserved, context)
            ]
        for instance in bound:
            concrete = instance.resolve(entry.driver_path)
            if PLACEHOLDER.search(concrete):
                continue
            set_here = instance.is_set(entry.driver_path)
            forbidden = instance.forbidden_by(entry)
            if set_here and forbidden:
                violated(concrete, f"{concrete} is forbidden when {_format(forbidden)}.")
            if not instance.applies(entry):
                continue
            if instance.requires(entry) and not set_here and entry.driver_path not in unread:
                condition = f" when {_format(entry.required_when)}" if entry.required_when else ""
                violated(concrete, f"{concrete} is required{condition}.")
            if not set_here:
                continue
            menu = registered.get(entry.driver_path) or set(entry.enum_values)
            value = _word(context.get(instance.resolve(entry.driver_path)))
            if entry.value_kind == "enum" and menu and _present(value) and value not in menu:
                source = "the supplied C++ registers" if entry.driver_path in registered else "the catalogue lists"
                violated(concrete, f"{concrete} is {value!r}, not one of the values {source}: {sorted(menu)}.")
            for sibling in entry.mutually_exclusive_with:
                if instance.is_set(sibling):
                    violated(concrete, f"{concrete} is mutually exclusive with {instance.resolve(sibling)}.")
            for sibling in entry.co_required_with:
                if not instance.is_set(sibling):
                    violated(concrete, f"{concrete} requires {instance.resolve(sibling)} to be set as well.")
    for path, reads in requirements.items():
        found += _scan_requirement(path, reads, context, document, built)
    return found
