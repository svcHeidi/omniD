"""``system/fvSchemes`` as every OpenFOAM-based solver reads it, through ``Foam::fvSchemes``.

The catalogue lists the ``default`` and the per-term entries of each scheme table. A value is a scheme's name followed by
what that scheme reads, so a menu is the names the table registers, and the parts of a value are judged through their own
tables (:func:`omnidriver.openfoam.case_rules.scheme_diagnostics`). Any other table or key of the dictionary is written as asked.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .case_rules import scheme_diagnostics
from .record_key_validation import CataloguedDocument, listed_entry
from .scheme_tables import committed_menus, cached_selection_tables, foam_source_root, SOURCE_ROOT_VARIABLE

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
    """``{table: {scheme name: attributes}}``: what OpenFOAM's authors state of a scheme (``openfoam_scheme_numerics.json``)."""
    return json.loads(NUMERICS_FILE.read_text())["attributes"]


def _entry(table: str, key: str) -> DictEntry:
    example, does = _TABLES[table]
    menu = tuple(committed_menus()["tables"][table])
    if key == "default":
        description = (
            f"The scheme for the {does} of {table} that have no key of their own; `{NO_DEFAULT}` leaves each to a key of its own. "
            "A value is a scheme's name followed by the words that scheme reads."
        )
        names = (*menu, NO_DEFAULT)
    else:
        description = (
            f"The scheme for one of the {does} in {table}, the key spelling the term as the solver names it, e.g. `{example}`. "
            "A value is a scheme's name followed by the words that scheme reads."
        )
        names = menu
    return DictEntry(
        driver_path=f"{table}.{key}",
        description=description,
        source_refs=_SOURCE,
        value_kind="string",
        enum_values=names,
        menu_attributes={name: attributes for name, attributes in _attributes().get(table, {}).items()},
        notes=(
            "The menu is the head of the value: the names OpenFOAM's own source registers for this table "
            "(src/finiteVolume), from openfoam_menus.json; a plan with $FOAM_SRC supplied judges the value against a fresh "
            "scan, each part through its own table. A value outside the menu is noted, never refused."
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
) -> tuple[StrictDiagnostic, ...]:
    """Notes for each scheme of the case's ``fvSchemes`` files that OpenFOAM's source ($FOAM_SRC, supplied) does not register.

    One note says so when the source is not supplied, and the schemes are then not judged."""
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
    found: list[StrictDiagnostic] = []
    for path in files:
        relpath = path.relative_to(case_root).as_posix()
        try:
            values = _read(path)
        except (OSError, ValueError, KeyError) as exc:
            found.append(diagnostic("error", "case_unreadable", f"{path} cannot be read: {exc}", source=relpath))
            continue
        found += scheme_diagnostics(values, menus, document=relpath, source_root=str(root))
    return tuple(found)
