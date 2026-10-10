"""OpenFOAM's own numerical-method names: the scheme tables of ``system/fvSchemes`` and the ``ODESolver`` table, read from
the ``finiteVolume`` and ``ODE`` libraries of ``$FOAM_SRC``.

A supplied ``$FOAM_SRC`` is scanned, and its tables are the menus every listing shows and every check judges against.
``openfoam_menus.json`` is the snapshot of one scan, written by ``python -m omnidriver.openfoam.scheme_tables`` (never typed)
with the OpenFOAM version and a digest of the source it read: a listing shows it, labelled, when no source is supplied,
and nothing is refused on its authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from . import dict_keys_scanner, rtst_scanner
from .rtst_scanner import scan_rtst_registrations, scan_scheme_registrations

#: The environment variable the sourced ``etc/bashrc`` sets to OpenFOAM's ``src``.
SOURCE_ROOT_VARIABLE = "FOAM_SRC"
#: The libraries of ``$FOAM_SRC`` whose registrations are read: every solver links them.
SCAN_LIBRARIES = ("finiteVolume", "ODE")
ODE_TABLE = "ODESolver"
MENUS_FILE = Path(__file__).with_name("openfoam_menus.json")
_SNAPSHOT_DESCRIPTION = (
    "A snapshot of OpenFOAM's scheme and ODESolver tables, scanned from the source whose version and digest it records. "
    "A listing shows it, labelled, when no $FOAM_SRC is supplied; nothing is judged against it."
)


@dataclass(frozen=True)
class SelectionTables:
    """``schemes``: ``{fvSchemes table: {name: class}}``; ``ode_solvers``: ``{name: class}``."""

    digest: str
    schemes: dict[str, dict[str, str]]
    ode_solvers: dict[str, str]

    def menus(self) -> dict[str, list[str]]:
        return {**{table: sorted(names) for table, names in self.schemes.items()}, ODE_TABLE: sorted(self.ode_solvers)}


def foam_source_root(environ: Mapping[str, str]) -> Path | None:
    """``$FOAM_SRC`` from the supplied environment, or ``None``; never searched for."""
    value = environ.get(SOURCE_ROOT_VARIABLE)
    return Path(value).expanduser().resolve() if value else None


def _files(source_root: Path):
    for library in SCAN_LIBRARIES:
        if (source_root / library).is_dir():
            yield from dict_keys_scanner.source_files(source_root / library)


def source_digest(source_root: Path) -> str:
    """A digest of the files of ``source_root`` the scan reads, by relative path and content."""
    digest = hashlib.sha256()
    for path in _files(source_root):
        digest.update(path.relative_to(source_root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _digest(source_root: Path) -> str:
    digest = hashlib.sha256()
    for module in (Path(__file__), Path(rtst_scanner.__file__), Path(dict_keys_scanner.__file__)):
        digest.update(module.read_bytes())
    digest.update(source_digest(source_root).encode())
    return digest.hexdigest()


def scan_selection_tables(source_root: Path, *, digest: str | None = None) -> SelectionTables:
    source_root = Path(source_root)
    texts = {
        path.relative_to(source_root).as_posix(): dict_keys_scanner._strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for path in _files(source_root)
    }
    return SelectionTables(
        digest=digest or _digest(source_root),
        schemes=scan_scheme_registrations(texts),
        ode_solvers=scan_rtst_registrations(texts).get(ODE_TABLE, {}),
    )


_MEMO: dict[tuple[str, str], SelectionTables] = {}
_SUPPLIED: dict[str, SelectionTables] = {}


def cached_selection_tables(source_root: Path, *, cache_root: Path | None) -> SelectionTables:
    """The tables of ``source_root``, kept under the supplied ``cache_root`` by a digest of the sources and the scanner; an
    unreadable cache file is rescanned and rewritten."""
    source_root = Path(source_root).resolve()
    digest = _digest(source_root)
    if (found := _MEMO.get((str(source_root), digest))) is not None:
        return found
    cache_file = Path(cache_root) / "openfoam-selection-scan" / f"{digest}.json" if cache_root is not None else None
    tables = None
    if cache_file is not None and cache_file.is_file():
        try:
            tables = SelectionTables(**json.loads(cache_file.read_text()))
        except (OSError, ValueError, TypeError):
            tables = None
        if tables is not None and tables.digest != digest:
            tables = None
    if tables is None:
        tables = scan_selection_tables(source_root, digest=digest)
        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=cache_file.parent, suffix=".tmp", delete=False) as handle:
                json.dump(asdict(tables), handle)
            os.replace(handle.name, cache_file)
    _MEMO[(str(source_root), digest)] = tables
    return tables


@lru_cache(maxsize=1)
def snapshot() -> dict:
    """``{"openfoam_version", "source_digest", "tables": {table: [names]}}`` as the snapshot's scan wrote them."""
    return json.loads(MENUS_FILE.read_text())


def snapshot_label() -> str:
    return f"the OpenFOAM {snapshot()['openfoam_version']} snapshot (openfoam_menus.json)"


def supplied_tables(environ: Mapping[str, str], *, cache_root: Path | None = None) -> SelectionTables | None:
    """The tables of the supplied ``$FOAM_SRC``, or ``None`` when none is supplied or it is not a directory. The scan is
    cached under ``cache_root``, by default the supplied scratch root."""
    root = foam_source_root(environ)
    if root is None or not root.is_dir():
        return None
    # One digest per source root and process: every listed entry and judged key asks.
    if (found := _SUPPLIED.get(str(root))) is None:
        found = _SUPPLIED[str(root)] = cached_selection_tables(
            root, cache_root=cache_root if cache_root is not None else dict_keys_scanner.scan_cache_root(),
        )
    return found


def table_menu(table: str, environ: Mapping[str, str]) -> tuple[tuple[str, ...], str | None]:
    """``(names, root)``: the names ``table`` registers in the supplied ``$FOAM_SRC`` and that root, or the snapshot's
    names and ``None`` when no source is supplied, which nothing may be refused against."""
    tables = supplied_tables(environ)
    if tables is None:
        return tuple(snapshot()["tables"].get(table, ())), None
    return tuple(tables.menus().get(table, ())), str(foam_source_root(environ))


def menu_source(table: str, environ: Mapping[str, str]) -> str:
    """What a listing says of where the menu of ``table`` comes from."""
    root = foam_source_root(environ)
    if root is not None and root.is_dir():
        return f"OpenFOAM's {table} table, scanned from {SOURCE_ROOT_VARIABLE}={root}"
    return (
        f"OpenFOAM's {table} table as {snapshot_label()} lists it; not judged, since {SOURCE_ROOT_VARIABLE} is not supplied"
    )


def version_mismatch(environ: Mapping[str, str]) -> str | None:
    """The running ``WM_PROJECT_VERSION`` when it is set and differs from the snapshot's version."""
    running = environ.get("WM_PROJECT_VERSION")
    return running if running and running != snapshot()["openfoam_version"] else None


def snapshot_diagnostics(environ: Mapping[str, str]) -> tuple[StrictDiagnostic, ...]:
    """A note when no source is supplied, so the snapshot stands in for the listings, and the running
    ``WM_PROJECT_VERSION`` is not the snapshot's version."""
    running = version_mismatch(environ)
    if running is None or supplied_tables(environ) is not None:
        return ()
    return (diagnostic(
        "info", "openfoam_snapshot_version_mismatch",
        f"the OpenFOAM menus listed are {snapshot_label()}, but the running OpenFOAM is {running}; "
        f"set {SOURCE_ROOT_VARIABLE} to its src for its own tables",
        detail={"snapshot": snapshot()["openfoam_version"], "running": running},
    ),)


@dataclass(frozen=True)
class OpenFoamTableEntry(DictEntry):
    """A key whose menu is one of OpenFOAM's selection tables (``table``): a word, judged against the table of a supplied
    ``$FOAM_SRC``, and listed with the snapshot's names, labelled, when none is supplied. ``enum_values`` is the snapshot's."""

    table: str = ""


def openfoam_table_entry(table: str, *, value_kind: str = "word", extra_values: tuple[str, ...] = (), **fields) -> OpenFoamTableEntry:
    """An :class:`OpenFoamTableEntry` whose ``enum_values`` are the snapshot's names of ``table`` and ``extra_values``."""
    return OpenFoamTableEntry(
        table=table, value_kind=value_kind, enum_values=(*snapshot()["tables"][table], *extra_values), **fields,
    )


def listed_menu(entry: OpenFoamTableEntry, environ: Mapping[str, str]) -> tuple[list[str], str]:
    """``(menu, menu_source)`` a listing shows for ``entry``: its table's names (:func:`table_menu`) and the values the
    entry adds to them."""
    snapshot_names = set(snapshot()["tables"].get(entry.table, ()))
    names, _root = table_menu(entry.table, environ)
    extras = [value for value in entry.enum_values if value not in snapshot_names]
    return [*names, *extras], menu_source(entry.table, environ)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m omnidriver.openfoam.scheme_tables <path to OpenFOAM src>", file=sys.stderr)
        return 2
    version = os.environ.get("WM_PROJECT_VERSION")
    if not version:
        print("WM_PROJECT_VERSION is not set: source the bashrc of the OpenFOAM whose src is scanned", file=sys.stderr)
        return 2
    tables = scan_selection_tables(Path(argv[1]))
    MENUS_FILE.write_text(json.dumps(
        {"description": _SNAPSHOT_DESCRIPTION, "openfoam_version": version, "source_digest": source_digest(Path(argv[1])), "tables": tables.menus()},
        indent=1, sort_keys=True,
    ) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
