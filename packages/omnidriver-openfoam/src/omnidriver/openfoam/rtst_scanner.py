"""OpenFOAM runtime-selection tables: every ``addToRunTimeSelectionTable`` registration, under its registered name.

The name is ``OverrideTypeName`` when the class declares one; a catalogue's enum menus are compared with the registrations.
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


def _class_extents(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, name)`` of each class body in ``text``, outermost first."""
    extents = []
    for match in _CLASS_DECL_RE.finditer(text):
        opened = text.find("{", match.end())
        if opened < 0:
            continue
        depth = 0
        for index in range(opened, len(text)):
            depth += (text[index] == "{") - (text[index] == "}")
            if depth == 0:
                extents.append((match.start(), index, match.group(1)))
                break
    return extents


def _declared_names(texts: Mapping[str, str], declaration: "re.Pattern[str]") -> dict[str, str]:
    """``{class: name}`` for each header's ``declaration`` (its first group), which belongs to the innermost class body holding it."""
    names: dict[str, str] = {}
    for relative, text in texts.items():
        if not relative.endswith(".H"):
            continue
        extents = _class_extents(text)
        for match in declaration.finditer(text):
            enclosing = [name for start, end, name in extents if start < match.start() < end]
            if enclosing:
                names[enclosing[-1]] = match.group(1)
    return names


def scan_rtst_registrations(texts: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """``{base: {registered name: derived class}}`` from comment-stripped
    sources keyed by relative path. An ``OverrideTypeName`` belongs to the
    nearest preceding class head in its header; a class without one
    registers under its own name."""
    override = _declared_names(texts, _OVERRIDE_TYPENAME_RE)
    registrations: dict[str, dict[str, str]] = {}
    for relative, text in sorted(texts.items()):
        if relative.endswith(".C"):
            for match in _RTST_RE.finditer(text):
                derived = match.group("derived")
                registrations.setdefault(match.group("base"), {})[override.get(derived, derived)] = derived
    return {base: dict(sorted(names.items())) for base, names in sorted(registrations.items())}


_TYPENAME_RE = re.compile(r'\bTypeName\s*\(\s*"([^"]+)"\s*\)')
# A scheme added to its table by hand, without a macro: `surfaceInterpolationScheme<scalar>::addMeshConstructorToTable<harmonic>`,
# or a solver's own gradient, `gradScheme<scalar>::addIstreamConstructorToTable<sealedWallLeastSquaresGrad>`.
_TABLE_ADDITION_RE = re.compile(
    r"\b(?P<base>surfaceInterpolationScheme|gradScheme)\s*<\s*\w+\s*>\s*::\s*add\w*ConstructorToTable\s*<\s*(?P<derived>\w+)\s*>",
)
_ADDED_TABLES = {"surfaceInterpolationScheme": "interpolationSchemes", "gradScheme": "gradSchemes"}
_MACRO_CALL_RE = re.compile(r'\b(make\w*Scheme\w*)\s*\(((?:[^()"]|"[^"]*")*)\)')

#: The registered name a scheme macro gives, by where it is written: ``type_name`` is the ``TypeName`` of the class
#: the first argument names; ``argument`` is the first argument itself (the macro stringifies it); ``limited_gradient``
#: is ``first<second>``; ``literal`` is the string that ends the call.
_NAME_FROM = {
    "type_name": lambda args, type_names: type_names.get(args[0], args[0]),
    "argument": lambda args, type_names: args[0],
    "limited_gradient": lambda args, type_names: f"{args[0]}<{args[1]}>",
    "literal": lambda args, type_names: args[-1].strip('"'),
}

#: Each of OpenFOAM's scheme registration macros: the table of ``system/fvSchemes`` it fills and how it names a scheme.
#: A macro in none of these (the multivariate schemes, a data table) registers into a table no fvSchemes entry names.
SCHEME_MACROS: dict[str, tuple[str, str]] = {
    "makeFvDdtScheme": ("ddtSchemes", "type_name"),
    "makeFvD2dt2Scheme": ("d2dt2Schemes", "type_name"),
    "makeFvGradScheme": ("gradSchemes", "type_name"),
    "makeFvLimitedGradScheme": ("gradSchemes", "limited_gradient"),
    "makeNamedFvLimitedGradTypeScheme": ("gradSchemes", "literal"),
    "makeLeastSquaresGradScheme": ("gradSchemes", "argument"),
    "makeSnGradScheme": ("snGradSchemes", "type_name"),
    "makeCentredFitSnGradScheme": ("snGradSchemes", "argument"),
    "makeFvLaplacianScheme": ("laplacianSchemes", "type_name"),
    "makeFvDivScheme": ("divSchemes", "type_name"),
    "makeFvConvectionScheme": ("divSchemes", "type_name"),
    "makeMultivariateFvConvectionScheme": ("divSchemes", "type_name"),
    **{macro: ("interpolationSchemes", "type_name") for macro in (
        "makeSurfaceInterpolationScheme", "makeSurfaceInterpolationTypeScheme",
        "makelimitedSurfaceInterpolationScheme", "makelimitedSurfaceInterpolationTypeScheme",
    )},
    **{macro: ("interpolationSchemes", "argument") for macro in (
        "makeLimitedSurfaceInterpolationScheme", "makeLimitedSurfaceInterpolationTypeScheme",
        "makeLimitedVSurfaceInterpolationScheme", "makeLLimitedSurfaceInterpolationTypeScheme",
        "makePhiSurfaceInterpolationScheme", "makeCentredFitSurfaceInterpolationScheme",
        "makeUpwindFitSurfaceInterpolationScheme", "makePureUpwindFitSurfaceInterpolationScheme",
    )},
}


def scan_scheme_registrations(texts: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """``{table: {registered name: class}}`` of OpenFOAM's ``make*Scheme`` registrations (:data:`SCHEME_MACROS`), from
    comment-stripped sources keyed by relative path, a table being the fvSchemes sub-dictionary that names its
    schemes (``ddtSchemes``, ``gradSchemes``, ...). A name is the ``TypeName`` of the class a macro names, or what the
    macro writes itself; the value is the macro's first argument, the scheme's class where it is one.
    A macro call a ``#define`` encloses registers nothing; a scheme added to its table by hand registers under its class's ``TypeName`` too."""
    type_names = _declared_names(texts, _TYPENAME_RE)
    tables: dict[str, dict[str, str]] = {}
    for relative, text in sorted(texts.items()):
        if not relative.endswith(".C"):
            continue
        for match in _MACRO_CALL_RE.finditer(text):
            rule = SCHEME_MACROS.get(match.group(1))
            args = [arg.strip() for arg in match.group(2).split(",")]
            if rule is None or not args[0] or (rule[1] == "limited_gradient" and len(args) < 2):
                continue
            table, how = rule
            name = _NAME_FROM[how](args, type_names)
            tables.setdefault(table, {})[name] = args[0]
        for match in _TABLE_ADDITION_RE.finditer(text):
            derived = match.group("derived")
            tables.setdefault(_ADDED_TABLES[match.group("base")], {})[type_names.get(derived, derived)] = derived
    return {table: dict(sorted(names.items())) for table, names in sorted(tables.items())}


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

    disagreements: list[str] = []
    uncatalogued: list[dict[str, Any]] = []
    values: dict[str, list[str]] = {}
    for path, rule in sorted(by_path.items()):
        base, mode = rule["base"], rule["mode"]
        if mode not in _MODES:
            disagreements.append(f"runtime_selection maps {path} with unknown mode {mode!r}")
        elif path not in enums:
            disagreements.append(f"runtime_selection maps {path}, which is not a catalogue enum")
        elif base not in registrations:
            disagreements.append(f"{path}: menu drawn from {base}, but no addToRunTimeSelectionTable({base}, ...) exists")
        else:
            registered = set(registrations[base])
            catalogued = set(enums[path].enum_values)
            values[path] = sorted(registered)
            if mode != "polymorphic" and catalogued - registered:
                disagreements.append(
                    f"{path}: menu lists {sorted(catalogued - registered)}, which {base} does not register"
                )
            if mode != "subset":
                uncatalogued += [
                    {"kind": "menu_value", "path": path, "value": name, "base": base,
                     "class": registrations[base][name]}
                    for name in sorted(registered - catalogued)
                ]
    disagreements += [
        f"runtime_selection lists {path} as not runtime-selected, which is not a catalogue enum"
        for path in sorted(not_selected) if path not in enums
    ]
    disagreements += [
        f"runtime_selection lists {base} as internal, but "
        + ("no table registers it" if base not in registrations else "it is also mapped")
        for base in sorted(internal) if base not in registrations or base in mapped_bases
    ]
    disagreements += [
        f"{path}: catalogue enum with no runtime_selection classification"
        for path in sorted(enums) if path not in by_path and path not in not_selected
    ]
    uncatalogued += [
        {"kind": "selection_table", "base": base, "values": sorted(registrations[base])}
        for base in sorted(registrations) if base not in mapped_bases and base not in internal
    ]
    return {"disagreements": disagreements, "uncatalogued": uncatalogued, "selector_values": values}
