"""OpenFOAM's own numerical-method names: the scheme tables of ``system/fvSchemes`` and the ``ODESolver`` table, read from
the ``finiteVolume`` and ``ODE`` libraries of ``$FOAM_SRC``.

``openfoam_menus.json`` is this scan of one OpenFOAM version, written by ``python -m omnidriver.openfoam.scheme_tables``
(never typed), so the menus are known without a source tree; a supplied ``$FOAM_SRC`` is scanned for the live names.
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

from . import dict_keys_scanner, rtst_scanner
from .rtst_scanner import scan_rtst_registrations, scan_scheme_registrations

#: The environment variable the sourced ``etc/bashrc`` sets to OpenFOAM's ``src``.
SOURCE_ROOT_VARIABLE = "FOAM_SRC"
#: The libraries of ``$FOAM_SRC`` whose registrations are read: every solver links them.
SCAN_LIBRARIES = ("finiteVolume", "ODE")
ODE_TABLE = "ODESolver"
MENUS_FILE = Path(__file__).with_name("openfoam_menus.json")


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


def _digest(source_root: Path) -> str:
    digest = hashlib.sha256()
    for module in (Path(__file__), Path(rtst_scanner.__file__), Path(dict_keys_scanner.__file__)):
        digest.update(module.read_bytes())
    for path in _files(source_root):
        digest.update(path.relative_to(source_root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
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
def committed_menus() -> dict:
    """``{"openfoam_version", "tables": {table: [names]}}`` as the committed scan wrote them."""
    return json.loads(MENUS_FILE.read_text())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m omnidriver.openfoam.scheme_tables <path to OpenFOAM src>", file=sys.stderr)
        return 2
    tables = scan_selection_tables(Path(argv[1]))
    MENUS_FILE.write_text(json.dumps(
        {"openfoam_version": os.environ.get("WM_PROJECT_VERSION", ""), "tables": tables.menus()}, indent=1, sort_keys=True,
    ) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
