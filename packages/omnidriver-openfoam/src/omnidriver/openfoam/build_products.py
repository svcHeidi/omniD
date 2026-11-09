"""What a wmake repository builds, which of its files a build reads, and what a case loads at run time:
the OpenFOAM layer's answers to ``get_solver_builds`` and ``get_extra_provenance_paths``, one for every
OpenFOAM-based solver."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from omnidriver.core.plugin_interface import RuntimeDependency, SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import file_digest, git_identity, recorded_build, tree_digest

_EXCLUDED = frozenset({"tutorials", "lnInclude", "platforms"})
_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})
_MAKE_FILES = frozenset({"files", "options"})
_EXE_RULE = re.compile(r"^\s*EXE\s*=\s*\$\((FOAM_(?:USER|MODULE)_APPBIN)\)/(\S+)", re.MULTILINE)
_LIB_RULE = re.compile(r"^\s*LIB\s*=\s*\$\((FOAM_(?:USER|MODULE)_LIBBIN)\)/(\S+)", re.MULTILINE)
_LIBRARY_SUFFIXES = (".so", ".dylib")
# wmake puts an unset FOAM_MODULE_* folder at the user one, so a library whose Make/files names
# FOAM_MODULE_LIBBIN can land in FOAM_USER_LIBBIN: search the folder the rule names, then the other.
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
    or user platform folders, looked for in the folder its rule names first; ``path`` is ``None`` when
    the product is in neither."""
    found: dict[str, Path | None] = {}
    for make_files in (path for path in _walk(Path(root)) if path.name == "files" and path.parent.name == "Make"):
        text = make_files.read_text(errors="replace")
        for named, name in _EXE_RULE.findall(text):
            found.setdefault(name, _first_file(folder / name for folder in _folders(env, named, _APP_FOLDERS)))
        for named, lib in _LIB_RULE.findall(text):
            found.setdefault(lib, _first_file(
                folder / (lib + suffix) for folder in _folders(env, named, _LIB_FOLDERS) for suffix in _LIBRARY_SUFFIXES))
    return list(found.items())


def _folders(env: Mapping[str, str], named: str, kinds: tuple[str, ...]) -> list[Path]:
    return [Path(env[name]) for name in (named, *(kind for kind in kinds if kind != named)) if env.get(name)]


def _first_file(candidates: Iterable[Path]) -> Path | None:
    return next((path for path in candidates if path.is_file()), None)


_SYSTEM_PREFIXES = ("/usr/lib/", "/System/", "/lib/", "/lib64/", "/usr/lib64/")
# Where OpenFOAM itself and its third-party libraries live; a library there is the install, not a build.
_INSTALL_VARIABLES = ("WM_PROJECT_DIR", "WM_THIRD_PARTY_DIR", "FOAM_LIBBIN", "FOAM_EXT_LIBBIN")
_OTOOL_LOAD = re.compile(r"^\s+(\S+) \(compatibility version")
_OTOOL_RPATH = re.compile(r"^\s+path (\S+) \(offset \d+\)")
_LDD_LINE = re.compile(r"^\s*\S+ => (/\S+) \(0x[0-9a-f]+\)")


def otool_libraries(text: str) -> list[str]:
    """The install names ``otool -L`` lists for one image (its own first line skipped)."""
    return [match.group(1) for line in text.splitlines()[1:] if (match := _OTOOL_LOAD.match(line))]


def otool_rpaths(text: str) -> list[str]:
    """The ``LC_RPATH`` entries of ``otool -l``, in load order."""
    return [match.group(1) for line in text.splitlines() if (match := _OTOOL_RPATH.match(line))]


def ldd_libraries(text: str) -> list[str]:
    """The files ``ldd`` resolved, in its order."""
    return [match.group(1) for line in text.splitlines() if (match := _LDD_LINE.match(line))]


def _run(argv: tuple[str, ...], env: Mapping[str, str]) -> str:
    try:
        done = subprocess.run(argv, env=dict(env), capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _resolve_install_name(name: str, image: Path, executable: Path, rpaths: list[str],
                          env: Mapping[str, str]) -> Path | None:
    # dyld's order: DYLD_LIBRARY_PATH by leaf name first, then @rpath through the image's rpaths, then the name.
    leaf = name.rsplit("/", 1)[-1]
    for folder in (entry for entry in env.get("DYLD_LIBRARY_PATH", "").split(os.pathsep) if entry):
        if (Path(folder) / leaf).is_file():
            return (Path(folder) / leaf).resolve()

    def expand(value: str) -> str:
        return value.replace("@executable_path", str(executable.parent)).replace("@loader_path", str(image.parent))

    if name.startswith("@rpath/"):
        rest = name[len("@rpath/"):]
        return next(((Path(expand(r)) / rest).resolve() for r in rpaths if (Path(expand(r)) / rest).is_file()), None)
    candidate = Path(expand(name))
    return candidate.resolve() if candidate.is_file() else None


def _direct_links(image: Path, executable: Path, env: Mapping[str, str]) -> list[Path]:
    if sys.platform == "darwin" and shutil.which("otool"):
        rpaths = otool_rpaths(_run(("otool", "-l", str(image)), env))
        names = otool_libraries(_run(("otool", "-L", str(image)), env))
        return [path for name in names if (path := _resolve_install_name(name, image, executable, rpaths, env))]
    if shutil.which("ldd"):
        return [Path(path) for path in ldd_libraries(_run(("ldd", str(image)), env)) if Path(path).is_file()]
    return []


def _is_install_or_system(path: Path, env: Mapping[str, str]) -> bool:
    text = str(path.resolve())
    roots = [str(Path(env[name]).resolve()) for name in _INSTALL_VARIABLES if env.get(name)]
    return text.startswith(_SYSTEM_PREFIXES) or any(text == root or text.startswith(root + os.sep) for root in roots)


def linked_libraries(binaries: Iterable[Path], env: Mapping[str, str]) -> list[Path]:
    """Every library ``binaries`` load at run time, followed through the libraries they load in turn,
    as the dynamic loader resolves it in ``env``; OpenFOAM's install and the system are left out."""
    found: dict[Path, Path] = {}
    pending = [(Path(binary), Path(binary)) for binary in binaries]
    seen: set[Path] = set()
    while pending:
        image, executable = pending.pop()
        if image.resolve() in seen:
            continue
        seen.add(image.resolve())
        for library in _direct_links(image, executable, env):
            if _is_install_or_system(library, env) or library.resolve() in found:
                continue
            found[library.resolve()] = library.resolve()
            pending.append((library, executable))
    return sorted(found.values())


def wmake_solver_builds(
    env: Mapping[str, str], *, repository: Any, used_paths: frozenset[Path] | None,
) -> tuple[SolverEntry, ...]:
    """The supplied repository's products as their build records state them; nothing without a
    repository, without products, or when the plan runs none of them.

    For a plan (``used_paths`` given), the products the run uses include the libraries its binaries load,
    and the libraries they load from outside the repository and the OpenFOAM install are a second entry,
    each by file and digest: which build of them a run loaded is part of what ran."""
    if repository is None:
        return ()
    root = Path(repository.root)
    built = products(root, env)
    if not built:
        return ()
    linked: list[Path] = []
    used = used_paths
    if used_paths is not None:
        linked = linked_libraries([path for _, path in built if path is not None and path.resolve() in used_paths], env)
        used = frozenset(used_paths) | frozenset(linked)
    selected = [
        (name, path) for name, path in built
        if used is None or (path is not None and path.resolve() in used)
    ]
    if not selected:
        return ()
    entries = [SolverEntry(
        solver=repository.plugin, repository=source_identity(root),
        builds=tuple(recorded_build(name, path) for name, path in selected), recordable=True,
    )]
    own = {path.resolve() for _, path in built if path is not None}
    outside = [library for library in linked if library not in own]
    if outside:
        entries.append(SolverEntry(
            solver=f"{repository.plugin} (linked libraries)", repository=None, recordable=False,
            builds=tuple(SolverBuild(name=library.name, path=library, digest=file_digest(library), known="unknown")
                         for library in outside),
        ))
    return tuple(entries)


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
