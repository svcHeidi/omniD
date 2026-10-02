#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     rtst_scanner
#
# Description
#     Scans runtime selection tables for available implementations.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""OpenFOAM runtime-selection tables: every ``addToRunTimeSelectionTable``
registration, under the name it registers (``OverrideTypeName`` when the
class declares one), and the comparison of a catalogue's enum menus with
them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

# `addToRunTimeSelectionTable(base, derived, ctor);` -- whitespace-tolerant
# including newlines.
_RTST_RE = re.compile(
    r"addToRunTimeSelectionTable\s*\(\s*"
    r"(?P<base>[A-Za-z_]\w*)\s*,\s*"
    r"(?P<derived>[A-Za-z_]\w*)\s*,\s*"
    r"(?P<ctor>[A-Za-z_]\w*)\s*\)",
)
_OVERRIDE_TYPENAME_RE = re.compile(r'OverrideTypeName\s*\(\s*"([^"]+)"\s*\)')
# A class head, not a forward declaration (`class Foo;`).
_CLASS_DECL_RE = re.compile(r"\bclass\s+([A-Za-z_]\w*)\b(?![^;{]*;)")


def scan_rtst_registrations(texts: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """``{base: {registered name: derived class}}`` from comment-stripped
    sources keyed by relative path. An ``OverrideTypeName`` belongs to the
    nearest preceding class head in its header; a class without one
    registers under its own name."""
    override: dict[str, str] = {}
    for relative, text in texts.items():
        if not relative.endswith(".H"):
            continue
        classes = [(match.start(), match.group(1)) for match in _CLASS_DECL_RE.finditer(text)]
        for match in _OVERRIDE_TYPENAME_RE.finditer(text):
            enclosing = [name for position, name in classes if position < match.start()]
            if enclosing:
                override[enclosing[-1]] = match.group(1)
    registrations: dict[str, dict[str, str]] = {}
    for relative, text in sorted(texts.items()):
        if relative.endswith(".C"):
            for match in _RTST_RE.finditer(text):
                derived = match.group("derived")
                registrations.setdefault(match.group("base"), {})[override.get(derived, derived)] = derived
    return {base: dict(sorted(names.items())) for base, names in sorted(registrations.items())}


# ---------------------------------------------------------------------------
# Catalogue side

#: How a catalogue enum's menu relates to the names its table registers.
#: strict: the same names. subset: the field offers a curated part of the
#: table. polymorphic: several tables share the selector, so the menu may
#: list names this table does not register.
_MODES = frozenset({"strict", "subset", "polymorphic"})


def runtime_selection_report(
    registrations: Mapping[str, Mapping[str, str]], *, entries: Iterable[Any], mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """A catalogue's enum menus against the C++ selection tables.

    ``registrations`` is ``{base: {registered name: derived class}}``;
    ``mapping`` is the reviewed ``runtime_selection`` section: ``by_path``
    (``driver_path`` -> ``{"base", "mode"}``), ``not_runtime_selected``
    (``driver_path`` -> why) and ``internal_bases`` (base -> why). A menu
    value no table registers, a mapped table that no longer exists, an
    unclassified enum or a stale mapping entry is a contradiction; a name a
    table registers that the menu lacks, and a table nothing maps, are
    uncatalogued."""
    enums = {
        entry.driver_path: entry for entry in entries
        if entry.value_kind == "enum" and entry.enum_values
    }
    by_path = dict(mapping.get("by_path", {}))
    not_selected = dict(mapping.get("not_runtime_selected", {}))
    internal = dict(mapping.get("internal_bases", {}))
    mapped_bases = {rule["base"] for rule in by_path.values()}

    contradictions: list[str] = []
    uncatalogued: list[dict[str, Any]] = []
    values: dict[str, list[str]] = {}
    for path, rule in sorted(by_path.items()):
        base, mode = rule["base"], rule["mode"]
        if mode not in _MODES:
            contradictions.append(f"runtime_selection maps {path} with unknown mode {mode!r}")
        elif path not in enums:
            contradictions.append(f"runtime_selection maps {path}, which is not a catalogue enum")
        elif base not in registrations:
            contradictions.append(f"{path}: menu drawn from {base}, but no addToRunTimeSelectionTable({base}, ...) exists")
        else:
            registered = set(registrations[base])
            catalogued = set(enums[path].enum_values)
            values[path] = sorted(registered)
            if mode != "polymorphic" and catalogued - registered:
                contradictions.append(
                    f"{path}: menu lists {sorted(catalogued - registered)}, which {base} does not register"
                )
            if mode != "subset":
                uncatalogued += [
                    {"kind": "menu_value", "path": path, "value": name, "base": base,
                     "class": registrations[base][name]}
                    for name in sorted(registered - catalogued)
                ]
    contradictions += [
        f"runtime_selection lists {path} as not runtime-selected, which is not a catalogue enum"
        for path in sorted(not_selected) if path not in enums
    ]
    contradictions += [
        f"runtime_selection lists {base} as internal, but "
        + ("no table registers it" if base not in registrations else "it is also mapped")
        for base in sorted(internal) if base not in registrations or base in mapped_bases
    ]
    contradictions += [
        f"{path}: catalogue enum with no runtime_selection classification"
        for path in sorted(enums) if path not in by_path and path not in not_selected
    ]
    uncatalogued += [
        {"kind": "selection_table", "base": base, "values": sorted(registrations[base])}
        for base in sorted(registrations) if base not in mapped_bases and base not in internal
    ]
    return {"contradictions": contradictions, "uncatalogued": uncatalogued, "selector_values": values}
