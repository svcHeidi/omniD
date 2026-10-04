"""The one evaluator of a catalogue's conditional logic and of the keys the C++ requires, over one resolved dictionary.

:func:`rule_diagnostics` names each violated relation per ``<name>`` instance, each missing C++ key and each enum value outside the menu.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.catalogue_paths import PLACEHOLDER, slot_key
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .literals import switch_value


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
        return any(switch_value(option) is actual for option in options)
    return actual in tuple(_word(option) for option in options)


def _format(predicate: Mapping[str, Any]) -> str:
    return " and ".join(
        f"{key} in ({', '.join(value)})" if isinstance(value, tuple) else f"{key}={value}"
        for key, value in predicate.items()
    )


def _instances(prefix: str, reserved: set[str], context: Mapping[str, Any]) -> list[str]:
    """Names under ``prefix`` with a leaf that no catalogued template spells literally."""
    names = set()
    for key in context:
        if key.startswith(prefix):
            name, _dot, rest = key[len(prefix):].partition(".")
            if rest and name not in reserved:
                names.add(name)
    return sorted(names)


class _Instance:
    """One entry bound to one concrete instance name of its ``<name>`` block, or to none outside any block.

    A predicate on a key the context lacks sees the key's ``default`` where the catalogue states one."""

    def __init__(
        self, context: Mapping[str, Any], defaults: Mapping[str, str],
        template: str | None = None, name: str | None = None,
    ):
        self.context = context
        self.defaults = defaults
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
            value = self.context[key] if key in self.context else self.defaults.get(slot_key(path))
            return value is not None and _matches(value, expected)
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


def _defaults(entries: Iterable[Any]) -> dict[str, str]:
    return {slot_key(entry.driver_path): entry.default for entry in entries if entry.default}


def applicable_entries(entries: Iterable[Any], context: Mapping[str, Any]) -> list[Any]:
    """The entries whose ``applicable_when`` holds in ``context`` and whose
    ``forbidden_when`` does not."""
    entries = tuple(entries)
    instance = _Instance(context, _defaults(entries))
    return [entry for entry in entries if instance.applies(entry)]


def forbidden_in(entries: Iterable[Any], context: Mapping[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    """Each entry ``context`` sets that its own ``forbidden_when`` forbids,
    with the predicates that hold."""
    entries = tuple(entries)
    instance = _Instance(context, _defaults(entries))
    return [(entry, forbidden) for entry in entries if instance.is_set(entry.driver_path) and (forbidden := instance.forbidden_by(entry))]


def match_dynamic_entry(key: str, entries: Iterable[Any]) -> tuple[Any, dict[str, str]] | None:
    """Match ``key`` against a ``dynamic_path`` entry's template, returning the
    entry and the concrete value each placeholder captured, or ``None``. The
    first match wins."""
    normalized = slot_key(key)
    for entry in entries:
        if not getattr(entry, "dynamic_path", False):
            continue
        entry_key = slot_key(entry.driver_path)
        placeholders = PLACEHOLDER.findall(entry_key)
        match = re.fullmatch(PLACEHOLDER.sub(r"([^.]+)", re.escape(entry_key)), normalized)
        if match:
            return entry, dict(zip(placeholders, match.groups()))
    return None


def _scan_facts(mapping: Any, entries: tuple[Any, ...], document: str, catalogue: Any):
    """What the supplied C++ adds to the catalogue's rules; nothing when the source is not supplied.
    ``catalogue`` is the plugin's, so that a read is told from one of another document."""
    from .dict_keys_scanner import (
        built_when, compared_menus, document_scans, registered_menus, required_reads, supplied_scan, unread_entries,
    )

    scan = supplied_scan(mapping)
    if scan is None:
        return {}, {}, {}, {}, set()
    reviewed = json.loads(Path(mapping.allowlist_path).read_text())
    name = document.rsplit("/", 1)[-1]
    documents = {**(catalogue.documents if catalogue is not None else {}), name: entries}
    found = document_scans(scan, documents)[name]
    compared = compared_menus(found, entries, reviewed)
    return (
        required_reads(scan, entries, document=name),
        registered_menus(reviewed, scan, entries),
        {path: menu.values for path, menu in compared.items()},
        built_when(reviewed, scan),
        {entry.driver_path for entry in unread_entries(found.scan, entries, reviewed)},
    )


def _scan_requirement(
    path: tuple[str, ...], reads: list[Any], context: Mapping[str, Any], document: str,
    built: Mapping[str, frozenset[str]],
) -> list[StrictDiagnostic]:
    """A key the C++ requires and the case lacks, in each block of the case that a class the case builds reads it from."""
    # A class is built when a selection table registers it under a name the case
    # selects, or when the scan or the plugin's reviewed ``built_when`` ties it to
    # a selector value the case holds. Inside a ``<name>`` block only that block's
    # values and those outside every block of its family count. A class nothing
    # ties to the case, and a read under a branch of its function, are noted, not judged.
    from .dict_keys_scanner import owner_of

    def ties(read: Any) -> frozenset[str] | None:
        if read.selected_as:
            return frozenset(name for _base, name in read.selected_as)
        return built.get(owner_of(read))

    segments = path[1:] if path[0].startswith("$") else path
    block, key = segments[:-1], segments[-1]
    wild = [PLACEHOLDER.fullmatch(s) is not None or s == "*" for s in block]
    pattern = re.compile(r"\.".join(r"[^.]+" if w else re.escape(s) for s, w in zip(block, wild)))
    blocks = sorted({
        ".".join(name.split(".")[:len(block)]) for name in context
        if len(name.split(".")) > len(block) and pattern.fullmatch(".".join(name.split(".")[:len(block)]))
    }) if block else [""]
    first = wild.index(True) if True in wild else None
    family = ".".join(block[:first]) + "." if first else ""
    reasons = {
        "not_tied": "the scan cannot tell whether this case builds the class that reads it",
        "branch": "the C++ reads it only under a condition of its own function",
    }
    found = []
    for scope in blocks:
        concrete = f"{scope}.{key}" if scope else key
        if _present(context.get(concrete)) or any(name.startswith(concrete + ".") for name in context):
            continue
        if first is not None:
            instance = ".".join(scope.split(".")[:first + 1]) + "."
            values = [v for k, v in context.items() if k.startswith(instance) or not k.startswith(family)]
        else:
            values = list(context.values())
        selected = {str(_word(value)) for value in values}
        groups: dict[str, list[Any]] = {"judged": [], "branch": [], "not_tied": []}
        for read in reads:
            names = ties(read)
            if (read.root or "").startswith("document:") or (names is not None and names & selected):
                groups["branch" if read.conditional else "judged"].append(read)
            elif names is None:
                groups["not_tied"].append(read)
        for name, group in groups.items():
            if not group:
                continue
            sources = ", ".join(sorted({f"{read.file}:{read.line} ({read.function})" for read in group}))
            lead = group[0]
            head = (
                f"{concrete} is read as {lead.method}<{lead.type or 'an unresolved type'}> with no default at "
                f"{sources}, and the catalogue does not list it (omnidriver catalog --uncatalogued describes it); "
            )
            tail = f" (below {path[0]})" if path[0].startswith("$") else ""
            if name == "judged":
                found.append(diagnostic(
                    "error", "cxx_required_key",
                    head + (
                        "the utility reads this document" if (lead.root or "").startswith("document:")
                        else "this case builds the class that reads it"
                    ) + f", so set {concrete} in {document}{tail}.",
                    source=document, field=concrete,
                ))
            else:
                found.append(diagnostic(
                    "info", "cxx_required_key_unjudged",
                    head + f"{reasons[name]}; if it applies, set {concrete} in {document}{tail}.",
                    source=document, field=concrete,
                ))
    return found


def rule_diagnostics(
    entries: Iterable[Any], context: Mapping[str, Any], *, document: str, mapping: Any = None,
    catalogue: Any = None,
) -> list[StrictDiagnostic]:
    """Every catalogue relation ``context`` (a dictionary's leaves, keyed by
    dotted path below the catalogue's scope token) violates, each enum value
    outside its menu and, when the plugin's ``mapping`` supplies its C++
    source, each key that C++ requires and ``context`` lacks. A menu is the names
    the C++ registers for the enum when its source is supplied and maps it to a
    selection table; otherwise the catalogue's, with the literals the C++ compares the value against.
    ``catalogue``, the plugin's ``DictionaryCatalog``, tells a read of this
    document from one of another."""
    entries = tuple(entries)
    requirements, registered, compared, built, unread = _scan_facts(mapping, entries, document, catalogue)
    templates = {
        key[: match.end()]
        for entry in entries if entry.dynamic_path
        for key in (slot_key(entry.driver_path),)
        for match in (PLACEHOLDER.search(key),) if match
    }
    defaults = _defaults(entries)
    found: list[StrictDiagnostic] = []
    unmet_groups: set[frozenset[str]] = set()

    def violated(field: str, message: str) -> None:
        found.append(diagnostic("error", "catalog_rule", message, source=document, field=field))

    for entry in entries:
        key = slot_key(entry.driver_path)
        match = PLACEHOLDER.search(key) if entry.dynamic_path else None
        if match is None:
            bound = [_Instance(context, defaults)]
        else:
            prefix = key[: match.start()]
            reserved = {
                segment for template in templates if template.startswith(prefix)
                for segment in (template[len(prefix):].split(".")[0],)
                if not PLACEHOLDER.fullmatch(segment)
            }
            bound = [
                _Instance(context, defaults, key[: match.end()], name)
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
            if entry.required_one_of:
                members = (entry.driver_path, *entry.required_one_of)
                group = frozenset(instance.resolve(member) for member in members)
                if group not in unmet_groups and not any(instance.is_set(member) for member in members):
                    unmet_groups.add(group)
                    violated(concrete, f"one of {', '.join(sorted(group))} is required.")
            if instance.requires(entry) and not set_here and entry.driver_path not in unread:
                condition = f" when {_format(entry.required_when)}" if entry.required_when else ""
                violated(concrete, f"{concrete} is required{condition}.")
            if not set_here:
                continue
            named = compared.get(entry.driver_path, frozenset())
            menu = registered.get(entry.driver_path) or set(entry.enum_values) | named
            value = _word(context.get(instance.resolve(entry.driver_path)))
            if entry.value_kind == "enum" and menu and _present(value) and value not in menu:
                source = (
                    "the supplied C++ registers" if entry.driver_path in registered
                    else "the catalogue lists or the supplied C++ compares" if named else "the catalogue lists"
                )
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
