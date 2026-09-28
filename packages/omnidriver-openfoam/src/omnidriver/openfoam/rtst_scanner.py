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

"""Scanner for OpenFOAM runtime-selection-table registrations.

For each `addToRunTimeSelectionTable(base, derived, ctor)` call in
`src/**/*.C` (skipping `lnInclude/` and `Make/`), this resolves the registered
type name used as the dictionary value (which may differ from the C++ class
name via `OverrideTypeName(...)`) by reading the derived class's header.

:func:`runtime_selection_report` compares a catalogue's ``enum`` entries with
those registrations, through the plugin's reviewed mapping (the
``runtime_selection`` section of its scanner allowlist). It runs inside the
strict dictionary-key report, so ``plan --strict`` checks it whenever the
source root is supplied, and ``omnidriver catalog`` shows the registered names.
Moved here from omnidriver-cardiacfoam 2026-09-28 (one reality): the
registration syntax is OpenFOAM's, not a solver's.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from typing import Any, Mapping


# `addToRunTimeSelectionTable(base, derived, ctor);` — argument layout is
# whitespace-tolerant including newlines.
_RTST_RE = re.compile(
    r"addToRunTimeSelectionTable\s*\(\s*"
    r"(?P<base>[A-Za-z_]\w*)\s*,\s*"
    r"(?P<derived>[A-Za-z_]\w*)\s*,\s*"
    r"(?P<ctor>[A-Za-z_]\w*)\s*\)",
    re.DOTALL,
)

_OVERRIDE_TYPENAME_RE = re.compile(
    r'OverrideTypeName\s*\(\s*"([^"]+)"\s*\)'
)

# `class Foo`, `class Foo final`, `class Foo : public Bar`, etc.
# Skip forward declarations (`class Foo;` with no `{`).
_CLASS_DECL_RE = re.compile(
    r"\bclass\s+([A-Za-z_]\w*)\b(?![^;{]*;)"
)


@dataclass(frozen=True)
class RtstReg:
    base: str
    registered_name: str
    derived_class: str
    source_file: Path


def _iter_src_files(src_root: Path, suffix: str) -> Iterable[Path]:
    for path in src_root.rglob(f"*{suffix}"):
        parts = path.parts
        if "lnInclude" in parts or "Make" in parts:
            continue
        yield path


def _index_override_type_names(src_root: Path) -> dict[str, str]:
    """Map *C++ class name* -> registered name (via `OverrideTypeName`).

    Each header is scanned for `class Foo { ... OverrideTypeName("X") ... }`
    patterns; each `OverrideTypeName` is paired with the nearest preceding
    `class <Name>` declaration in the same file. This handles the general
    case where a model's C++ class name could differ from its registered
    type string, and works uniformly for the common case (`BuenoOrovio`,
    `ORd`, `PerisYague`, …) where the class name and the override name are
    the same.

    Classes without an `OverrideTypeName` simply do not appear in the
    index; the caller falls back to the class name.
    """
    index: dict[str, str] = {}
    for header in _iter_src_files(src_root, ".H"):
        text = header.read_text(encoding="utf-8", errors="replace")
        # Strip comments first so commented-out code never matches.
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//[^\n]*", "", text)
        class_positions: list[tuple[int, str]] = [
            (m.start(), m.group(1)) for m in _CLASS_DECL_RE.finditer(text)
        ]
        if not class_positions:
            continue
        for override in _OVERRIDE_TYPENAME_RE.finditer(text):
            pos = override.start()
            # Nearest preceding class declaration.
            enclosing = None
            for cls_pos, cls_name in class_positions:
                if cls_pos < pos:
                    enclosing = cls_name
                else:
                    break
            if enclosing is not None:
                index[enclosing] = override.group(1)
    return index


def scan_rtst_registrations(
    src_root: Path,
) -> dict[str, dict[str, RtstReg]]:
    """Return `{base_class: {registered_name: RtstReg}}` for every RTST
    registration found under `src_root`.
    """
    override_map = _index_override_type_names(src_root)
    out: dict[str, dict[str, RtstReg]] = {}
    for source in _iter_src_files(src_root, ".C"):
        text = source.read_text(encoding="utf-8", errors="replace")
        # Strip block comments so we don't pick up commented-out
        # registrations.
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//[^\n]*", "", text)
        for match in _RTST_RE.finditer(text):
            base = match.group("base")
            derived = match.group("derived")
            registered = override_map.get(derived, derived)
            out.setdefault(base, {})[registered] = RtstReg(
                base=base,
                registered_name=registered,
                derived_class=derived,
                source_file=source,
            )
    return out


# ---------------------------------------------------------------------------
# Catalogue side

#: How a catalogue enum's values relate to the registered names of its base.
#: strict: equal. subset: the catalogue lists some of them (one field exposes
#: a curated part of a table). polymorphic: the catalogue lists all of them,
#: and may list more (several tables share one selector).
_MODES = frozenset({"strict", "subset", "polymorphic"})


def runtime_selection_report(
    src_root: Path, *, entries: Iterable[Any], mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Drift between a catalogue's enum entries and the C++ registrations.

    ``mapping`` is the reviewed ``runtime_selection`` section: ``by_path``
    (``driver_path`` -> ``{"base", "mode"}``), ``not_runtime_selected``
    (``driver_path`` -> why) and ``internal_bases`` (base -> why). Each drift
    list is empty when the catalogue and the C++ agree; ``selector_values``
    maps every checked ``driver_path`` to the names the C++ registers.
    """
    registrations = scan_rtst_registrations(src_root)
    enums = {
        entry.driver_path: entry for entry in entries
        if entry.value_kind == "enum" and entry.enum_values
    }
    by_path = dict(mapping.get("by_path", {}))
    not_selected = dict(mapping.get("not_runtime_selected", {}))
    internal = dict(mapping.get("internal_bases", {}))
    mapped_bases = {rule["base"] for rule in by_path.values()}

    drift: list[str] = []
    unused: list[str] = []
    values: dict[str, list[str]] = {}
    for path, rule in sorted(by_path.items()):
        base, mode = rule["base"], rule["mode"]
        if mode not in _MODES:
            drift.append(f"{path}: unknown comparison mode {mode!r}")
            continue
        if path not in enums:
            unused.append(f"by_path:{path}")
            continue
        if base not in registrations:
            drift.append(f"{path}: no addToRunTimeSelectionTable({base}, ...) found")
            continue
        registered = set(registrations[base])
        catalogued = set(enums[path].enum_values)
        values[path] = sorted(registered)
        only_catalogue = sorted(catalogued - registered)
        only_cxx = sorted(registered - catalogued)
        if (mode == "strict" and (only_catalogue or only_cxx)) or (
            mode == "subset" and only_catalogue
        ) or (mode == "polymorphic" and only_cxx):
            drift.append(
                f"{path} ({mode}, {base}): catalogue only {only_catalogue}; C++ only {only_cxx}"
            )
    unused += [f"not_runtime_selected:{path}" for path in sorted(not_selected) if path not in enums]
    unused += [
        f"internal_bases:{base}" for base in sorted(internal)
        if base not in registrations or base in mapped_bases
    ]
    return {
        "selector_drift": drift,
        "unclassified_selector_enums": sorted(
            path for path in enums if path not in by_path and path not in not_selected
        ),
        "unmapped_selector_bases": sorted(
            base for base in registrations if base not in mapped_bases and base not in internal
        ),
        "unused_selector_mapping": unused,
        "selector_values": values,
    }
