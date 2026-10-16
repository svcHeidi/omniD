"""What a wmake repository builds and which of its files a build reads: the OpenFOAM layer's
answer to ``get_solver_builds``, one for every OpenFOAM-based solver."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterator, Mapping

from omnidriver.core.plugin_interface import SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import git_identity, recorded_build, tree_digest

_EXCLUDED = frozenset({"tutorials", "lnInclude", "platforms", ".git"})
_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})
_MAKE_FILES = frozenset({"files", "options"})
_EXE_RULE = re.compile(r"^\s*EXE\s*=\s*\$\(FOAM_USER_APPBIN\)/(\S+)", re.MULTILINE)
_LIB_RULE = re.compile(r"^\s*LIB\s*=\s*\$\(FOAM_USER_LIBBIN\)/(\S+)", re.MULTILINE)
_LIBRARY_SUFFIXES = (".so", ".dylib")


def _walk(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _EXCLUDED)
        for name in sorted(filenames):
            yield Path(dirpath, name)


def build_source_files(root: Path) -> list[Path]:
    """Every C++/CUDA source and ``Make/files``/``Make/options`` a build of ``root`` reads; tutorials,
    ``lnInclude`` links and platform products are not source."""
    return [
        path for path in _walk(Path(root))
        if path.suffix in _SOURCE_SUFFIXES or (path.parent.name == "Make" and path.name in _MAKE_FILES)
    ]


def source_identity(root: Path) -> SourceIdentity:
    """The repository at ``root``: its build-source digest and git identity."""
    root = Path(root).resolve()
    return SourceIdentity(repository=str(root), digest=tree_digest(root, build_source_files(root)), git=git_identity(root))


def products(root: Path, env: Mapping[str, str]) -> list[tuple[str, Path | None]]:
    """``(name, path)`` for every ``EXE``/``LIB`` a ``Make/files`` under ``root`` builds into the user
    platform folders; ``path`` is ``None`` when the product is not there."""
    appbin, libbin = env.get("FOAM_USER_APPBIN"), env.get("FOAM_USER_LIBBIN")
    found: dict[str, Path | None] = {}
    for make_files in (path for path in _walk(Path(root)) if path.name == "files" and path.parent.name == "Make"):
        text = make_files.read_text(errors="replace")
        for name in _EXE_RULE.findall(text):
            path = Path(appbin, name) if appbin else None
            found.setdefault(name, path if path is not None and path.is_file() else None)
        for lib in _LIB_RULE.findall(text):
            path = next((Path(libbin, lib + suffix) for suffix in _LIBRARY_SUFFIXES
                         if libbin and Path(libbin, lib + suffix).is_file()), None)
            found.setdefault(lib, path)
    return list(found.items())


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
