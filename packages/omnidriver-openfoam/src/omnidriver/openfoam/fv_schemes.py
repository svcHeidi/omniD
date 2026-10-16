"""``system/fvSchemes`` as every OpenFOAM-based solver reads it, through ``Foam::fvSchemes``.

The catalogue lists the ``default`` and the per-term entries of each scheme table. A value is a scheme's name followed by
what that scheme reads, so a menu is the names the table registers, and the parts of a value are judged through their own
tables (:func:`omnidriver.openfoam.case_rules.scheme_diagnostics`). Any other table or key of the dictionary is written as asked.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Iterable, Mapping

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .case_rules import SCHEME_ARGUMENTS, scheme_diagnostics, scheme_parts
from .record_key_validation import CataloguedDocument, listed_entry
from .scheme_tables import SOURCE_ROOT_VARIABLE, cached_selection_tables, foam_source_root, openfoam_table_entry

FV_SCHEMES_DOCUMENT: Final = "system/fvSchemes"
TERM: Final = "<term>"

#: Each table of ``fvSchemes`` that names schemes, with the form of the term a per-term key spells and what the table does.
_TABLES: Final = {
    "ddtSchemes": ("ddt(Vm)", "time derivatives"),
    "gradSchemes": ("grad(Vm)", "gradients"),
    "divSchemes": ("div(phi,U)", "divergences and convection"),
    "laplacianSchemes": ("laplacian(D,Vm)", "laplacians"),
    "snGradSchemes": ("snGrad(Vm)", "face-normal gradients"),
    "interpolationSchemes": ("interpolate(Vm)", "interpolations of a field onto the faces"),
}
TABLES: Final = tuple(_TABLES)

#: ``default none`` is OpenFOAM's explicit "no default" (``schemesLookupDetail.C``, which tests ``peek() == "none"``).
NO_DEFAULT: Final = "none"
_SOURCE = ("src/OpenFOAM/matrices/schemes/schemesLookup.C", "src/OpenFOAM/matrices/schemes/schemesLookupDetail.C")


NUMERICS_FILE: Final = Path(__file__).with_name("openfoam_scheme_numerics.json")


@lru_cache(maxsize=1)
def _attributes() -> dict[str, dict[str, dict[str, Any]]]:
    """``{table: {scheme name: attributes}}``: what OpenFOAM's authors state of a scheme (``openfoam_scheme_numerics.json``),
    with a ``composes`` for each scheme with an order that reads other schemes (:data:`case_rules.SCHEME_ARGUMENTS`)."""
    attributes = json.loads(NUMERICS_FILE.read_text())["attributes"]
    for table, schemes in attributes.items():
        for name, stated in schemes.items():
            reads = SCHEME_ARGUMENTS.get(table, {}).get(name)
            if reads and "formal_order" in stated:
                stated["composes"] = {
                    "kind": "inferred",
                    "reads": list(reads),
                    "statement": (
                        f"the order is bounded by the orders of the {' and '.join(reads)} schemes the value names after "
                        f"{name}; the header's order assumes them"
                    ),
                    "basis": next(source["text"] for source in stated["stated_by"] if source["kind"] == "header"),
                }
    return attributes


def _entry(table: str, key: str) -> DictEntry:
    example, does = _TABLES[table]
    if key == "default":
        description = (
            f"The scheme for the {does} of {table} that have no key of their own; `{NO_DEFAULT}` leaves each to a key of its own. "
            "A value is a scheme's name followed by the words that scheme reads."
        )
    else:
        description = (
            f"The scheme for one of the {does} in {table}, the key spelling the term as the solver names it, e.g. `{example}`. "
            "A value is a scheme's name followed by the words that scheme reads."
        )
    return openfoam_table_entry(
        table,
        value_kind="string",
        extra_values=(NO_DEFAULT,) if key == "default" else (),
        driver_path=f"{table}.{key}",
        description=description,
        source_refs=_SOURCE,
        menu_attributes={name: attributes for name, attributes in _attributes().get(table, {}).items()},
        notes=(
            "The menu is the head of the value: the names OpenFOAM's source registers for this table (src/finiteVolume). "
            "A plan judges each part of the value through its own table when $FOAM_SRC is supplied; a value outside the menu "
            "is a warning, never a refusal."
        ),
        phases=frozenset({"solver"}),
        allowed_bindings={TERM: None} if key == TERM else {},
    )


FV_SCHEMES_ENTRIES: Final[tuple[DictEntry, ...]] = tuple(
    _entry(table, key) for table in _TABLES for key in ("default", TERM)
)
FV_SCHEMES_ENTRIES_BY_PATH: Final = {entry.driver_path: entry for entry in FV_SCHEMES_ENTRIES}


def ddt_stability_limits() -> dict[str, float]:
    """``{ddt scheme: the largest rate * deltaT}`` for which the scheme's operator stays stable when a linear decay ``rate``
    acts on the old time level, for each scheme that has a limit recorded."""
    return {
        name: attributes["stability"]["decay_on_old_level_rate_dt_max"]
        for name, attributes in FV_SCHEMES_ENTRIES_BY_PATH["ddtSchemes.default"].menu_attributes.items()
        if "decay_on_old_level_rate_dt_max" in attributes.get("stability", {})
    }


def stated_numerics(table: str, value: Any) -> list[dict[str, Any]]:
    """What is stated of each scheme an ``fvSchemes`` value names (:func:`case_rules.scheme_parts`), its argument
    conditions applied: ``{"table", "name", "arguments"}`` and the scheme's attributes, with ``formal_order`` and
    ``equivalent_to`` only where a ``when`` of its ``by_argument`` holds for the arguments written."""
    resolved = []
    for part_table, name, words in scheme_parts(table, value):
        attributes = dict(_attributes().get(part_table, {}).get(name, {}))
        names = attributes.pop("arguments", [])
        arguments = {argument: float(word) for argument, word in zip(names, words)}
        for case in attributes.pop("by_argument", []):
            if all(arguments.get(argument) == expected for argument, expected in case["when"].items()):
                attributes.update({key: item for key, item in case.items() if key != "when"})
        resolved.append({"table": part_table, "name": name, "arguments": arguments, **attributes})
    return resolved


def _match(key_path: tuple[str, ...]) -> tuple[DictEntry, dict[str, str]] | None:
    if len(key_path) != 2 or key_path[0] not in _TABLES:
        return None
    table, key = key_path
    if key == "default":
        return FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.default"], {}
    return FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.{TERM}"], {TERM: key}


def fv_schemes_document() -> CataloguedDocument:
    """The ``record_key_validator`` document: each table's keys by kind, any other key unvalidated."""
    return CataloguedDocument(
        label="fvSchemes", entries=FV_SCHEMES_ENTRIES_BY_PATH.values, match=_match, scan=lambda key_path: key_path, open=True,
    )


def fv_schemes_listing(case_root: Any) -> tuple[dict[str, Any], ...]:
    """The catalogued keys a study may set in the case's ``fvSchemes``; none when the case has no such file."""
    if not (Path(case_root) / FV_SCHEMES_DOCUMENT).is_file():
        return ()
    return tuple(listed_entry(FV_SCHEMES_DOCUMENT, path, entry) for path, entry in FV_SCHEMES_ENTRIES_BY_PATH.items())


def _read(path: Path) -> dict[str, dict[str, Any]]:
    from foamlib import FoamFile

    parsed = FoamFile(path)
    return {
        table: {key: parsed[table][key] for key in parsed[table].keys() if key is not None}
        for table in TABLES if table in parsed.keys() and hasattr(parsed[table], "keys")
    }


def fv_schemes_diagnostics(
    case_root: Path, *, env: Mapping[str, str], scratch_root: Path | None,
    solver_schemes: Mapping[str, Iterable[str]] | None = None, solver_root: Path | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """Notes for each scheme of the case's ``fvSchemes`` files that OpenFOAM's source ($FOAM_SRC, supplied) does not register.

    ``solver_schemes`` (``{table: names}``) are the schemes the solver's own source at ``solver_root`` adds to those
    tables, which a case may name too. One note says so when OpenFOAM's source is not supplied, and the schemes are then
    not judged."""
    files = sorted((Path(case_root) / "system").rglob("fvSchemes")) if (Path(case_root) / "system").is_dir() else []
    if not files:
        return ()
    root = foam_source_root(env)
    if root is None:
        return (diagnostic(
            "info", "openfoam_source_not_supplied",
            f"fvSchemes not judged against OpenFOAM's scheme tables: source root not supplied (source OpenFOAM's bashrc, "
            f"or set {SOURCE_ROOT_VARIABLE} to its src)",
            source=FV_SCHEMES_DOCUMENT,
        ),)
    if not root.is_dir():
        return (diagnostic(
            "warning", "openfoam_source_unavailable",
            f"{SOURCE_ROOT_VARIABLE} is supplied, but {root} is not a directory, so fvSchemes is not judged",
            source=FV_SCHEMES_DOCUMENT,
        ),)
    tables = cached_selection_tables(root, cache_root=scratch_root)
    menus = {table: set(names) for table, names in tables.menus().items()}
    for table, names in (solver_schemes or {}).items():
        menus.setdefault(table, set()).update(names)
    registered_in = f"{root}" + (f" and the solver's {solver_root}" if solver_schemes else "")
    found: list[StrictDiagnostic] = []
    for path in files:
        relpath = path.relative_to(case_root).as_posix()
        try:
            values = _read(path)
        except (OSError, ValueError, KeyError) as exc:
            found.append(diagnostic("error", "case_unreadable", f"{path} cannot be read: {exc}", source=relpath))
            continue
        found += scheme_diagnostics(values, menus, document=relpath, source_root=registered_in)
    return tuple(found)
