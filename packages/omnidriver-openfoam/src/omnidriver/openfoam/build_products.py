"""What a wmake repository builds, which of its files a build reads, and what a case loads at run time:
the OpenFOAM layer's answers to ``get_solver_builds`` and ``get_extra_provenance_paths``, one for every
OpenFOAM-based solver."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from omnidriver.core.plugin_interface import RuntimeDependency, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import git_identity, recorded_build, tree_digest

_EXCLUDED = frozenset({"tutorials", "lnInclude", "platforms"})
_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})
_MAKE_FILES = frozenset({"files", "options"})
_EXE_RULE = re.compile(r"^\s*EXE\s*=\s*\$\(FOAM_(?:USER|MODULE)_APPBIN\)/(\S+)", re.MULTILINE)
_LIB_RULE = re.compile(r"^\s*LIB\s*=\s*\$\(FOAM_(?:USER|MODULE)_LIBBIN\)/(\S+)", re.MULTILINE)
_LIBRARY_SUFFIXES = (".so", ".dylib")
# wmake puts an unset FOAM_MODULE_* folder at the user one, so a library whose Make/files names
# FOAM_MODULE_LIBBIN can land in FOAM_USER_LIBBIN: search every defined folder.
_APP_FOLDERS = ("FOAM_MODULE_APPBIN", "FOAM_USER_APPBIN")
_LIB_FOLDERS = ("FOAM_MODULE_LIBBIN", "FOAM_USER_LIBBIN")


def _walk(root: Path) -> Iterator[Path]:
    # A hidden folder (.git, an agent's .claude/worktrees) and a nested checkout or submodule (a
    # folder with its own .git, built separately) are not what a build of root reads.
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in _EXCLUDED and not name.startswith(".") and not Path(dirpath, name, ".git").exists()
        )
        for name in sorted(filenames):
            yield Path(dirpath, name)


def build_source_files(root: Path) -> list[Path]:
    """Every C++/CUDA source and ``Make/files``/``Make/options`` a build of ``root`` reads; tutorials,
    ``lnInclude`` links, platform products, hidden folders and nested checkouts are not source."""
    return [
        path for path in _walk(Path(root))
        if path.suffix in _SOURCE_SUFFIXES or (path.parent.name == "Make" and path.name in _MAKE_FILES)
    ]


def source_identity(root: Path) -> SourceIdentity:
    """The repository at ``root``: its build-source digest and git identity."""
    root = Path(root).resolve()
    return SourceIdentity(repository=str(root), digest=tree_digest(root, build_source_files(root)), git=git_identity(root))


def products(root: Path, env: Mapping[str, str]) -> list[tuple[str, Path | None]]:
    """``(name, path)`` for every ``EXE``/``LIB`` a ``Make/files`` under ``root`` builds into the module
    or user platform folders; ``path`` is ``None`` when the product is in neither."""
    appbins = [Path(env[name]) for name in _APP_FOLDERS if env.get(name)]
    libbins = [Path(env[name]) for name in _LIB_FOLDERS if env.get(name)]
    found: dict[str, Path | None] = {}
    for make_files in (path for path in _walk(Path(root)) if path.name == "files" and path.parent.name == "Make"):
        text = make_files.read_text(errors="replace")
        for name in _EXE_RULE.findall(text):
            found.setdefault(name, _first_file(folder / name for folder in appbins))
        for lib in _LIB_RULE.findall(text):
            found.setdefault(lib, _first_file(folder / (lib + suffix) for folder in libbins for suffix in _LIBRARY_SUFFIXES))
    return list(found.items())


def _first_file(candidates: Iterable[Path]) -> Path | None:
    return next((path for path in candidates if path.is_file()), None)


def wmake_solver_builds(
    env: Mapping[str, str], *, repository: Any, used_paths: frozenset[Path] | None,
) -> tuple[SolverEntry, ...]:
    """The supplied repository's products as their build records state them; nothing without a
    repository, without products, or when the plan runs none of them."""
    if repository is None:
        return ()
    root = Path(repository.root)
    built = products(root, env)
    if not built:
        return ()
    selected = [
        (name, path) for name, path in built
        if used_paths is None or (path is not None and path.resolve() in used_paths)
    ]
    if not selected:
        return ()
    return (SolverEntry(
        solver=repository.plugin, repository=source_identity(root),
        builds=tuple(recorded_build(name, path) for name, path in selected), recordable=True,
    ),)


# FOAM_LIBBIN too: a controlDict may load one of OpenFOAM's own libraries.
_LOADED_LIB_FOLDERS = (*_LIB_FOLDERS, "FOAM_LIBBIN")
_BARE_LIB = re.compile(r"^lib(.+)\.(?:so|dylib)$")
_VARIABLE = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _control_dict_libs(control_dict: Path) -> tuple[str, ...]:
    """The entries of a controlDict's ``libs ( ... )``; an absent or unparseable list gives ``()``."""
    from foamlib import FoamFile

    try:
        libs = FoamFile(control_dict).get("libs")
    except (OSError, ValueError):
        return ()
    return tuple(str(entry).strip('"') for entry in libs or ())


def _expanded(raw: str, *, case_root: Path, env: Mapping[str, str]) -> str | None:
    """``raw`` with each ``$VAR`` from ``env``, ``$FOAM_CASE`` being ``case_root``; ``None`` when one is undefined."""
    # etc/bashrc does not set $FOAM_CASE: OpenFOAM substitutes it at solver startup.
    missing: list[str] = []

    def substitute(match: "re.Match[str]") -> str:
        name = match.group(1) or match.group(2)
        value = str(case_root) if name == "FOAM_CASE" else env.get(name)
        if value is None:
            missing.append(name)
            return ""
        return value

    expanded = _VARIABLE.sub(substitute, raw)
    return None if missing else expanded


def _loaded_library(entry: str, *, case_root: Path, env: Mapping[str, str]) -> RuntimeDependency:
    basename = entry.rsplit("/", 1)[-1]
    match = _BARE_LIB.match(basename)
    name = match.group(1) if match else basename
    if "/" not in entry:
        folders = [Path(env[folder]) for folder in _LOADED_LIB_FOLDERS if env.get(folder)]
        path = _first_file(folder / f"lib{name}{suffix}" for folder in folders for suffix in _LIBRARY_SUFFIXES)
    else:
        expanded = _expanded(entry, case_root=case_root, env=env)
        path = Path(expanded) if expanded is not None and Path(expanded).is_file() else None
    return RuntimeDependency(name=name, path=path, required=True)


def case_runtime_dependencies(case_root: Path, *, env: Mapping[str, str]) -> tuple[RuntimeDependency, ...]:
    """What the case itself says it loads: each library its ``system/controlDict`` ``libs`` names, and gmsh when it
    carries a ``.geo``. Each is required, since the case cannot run without it; one not found is reported unavailable,
    never omitted."""
    case_root = Path(case_root)
    control_dict = case_root / "system" / "controlDict"
    found = [
        _loaded_library(entry, case_root=case_root, env=env)
        for entry in (_control_dict_libs(control_dict) if control_dict.is_file() else ())
    ]
    if any(case_root.rglob("*.geo")):
        gmsh = shutil.which("gmsh", path=env.get("PATH"))
        found.append(RuntimeDependency(name="gmsh", path=Path(gmsh) if gmsh else None, required=True))
    return tuple(found)
