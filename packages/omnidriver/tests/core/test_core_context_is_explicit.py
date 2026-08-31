"""core/ and openfoam/ must receive an explicit DriverContext, never resolve
one implicitly.

`resolve_public_driver_context(None)` returns the cardiac context. A core
module that calls it silently becomes cardiacFoam for any plugin that failed
to thread a context through -- and it does so without raising, which is why
this guard is static rather than behavioural.

The cardiac default is legitimate at the public edge (omnidriver/*.py and
cli.py), where "no plugin supplied" genuinely means "the built-in one". It is
not legitimate inside core/ -- nor inside omnidriver-openfoam, whose three
former offenders (apply_overrides.py's `_catalog_entries`/`apply_overrides`,
dict_builder.py's `is_known_override_driver_path`) made a core+openfoam
install without cardiacfoam silently import `omnidriver.cardiacfoam` (Phase 2
Task 6). That is a wrong-direction dependency the import-boundary gate cannot
see, because openfoam imports *core* and core does the cardiac import --
this guard is the only thing standing between openfoam and that regression.
"""
from __future__ import annotations

import ast
import pathlib

import omnidriver.core

_CORE_ROOT = pathlib.Path(omnidriver.core.__file__).resolve().parent

# compatibility.py defines the function; it is allowed to mention its own name.
_EXEMPT = {_CORE_ROOT / "compatibility.py"}

# omnidriver.openfoam is not importable in a core-only venv, so this is
# resolved from the repo layout rather than by importing the package.
# core/__init__.py's ancestors are core, omnidriver, src, omnidriver (the
# package directory), packages -- parents[4] is "packages". parents[3] would
# land on packages/omnidriver/ and silently yield a path that does not
# exist, which would make this guard pass by scanning zero files -- the
# exact false-reassurance failure mode this repository has hit before, so
# _OPENFOAM_ROOT.is_dir() is asserted below rather than assumed.
_OPENFOAM_ROOT = (
    pathlib.Path(omnidriver.core.__file__).resolve().parents[4]
    / "omnidriver-openfoam" / "src" / "omnidriver" / "openfoam"
)


def _calls_resolve_public(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "resolve_public_driver_context":
            lines.append(node.lineno)
    return lines


def _offenders(root: pathlib.Path, *, exempt: set[pathlib.Path]) -> dict[str, list[int]]:
    offenders: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        if path in exempt or "__pycache__" in path.parts:
            continue
        hits = _calls_resolve_public(path)
        if hits:
            offenders[str(path.relative_to(root))] = hits
    return offenders


def test_core_never_resolves_an_implicit_driver_context() -> None:
    offenders = _offenders(_CORE_ROOT, exempt=_EXEMPT)
    assert offenders == {}, (
        "core/ modules resolving an implicit (cardiac) DriverContext:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nMake driver_context a required parameter instead."
    )


def test_openfoam_never_resolves_an_implicit_driver_context() -> None:
    assert _OPENFOAM_ROOT.is_dir(), (
        f"expected omnidriver-openfoam's source tree at {_OPENFOAM_ROOT}, but "
        "it is not a directory -- a guard that silently scans zero files is "
        "worse than no guard. Fix the path computation rather than letting "
        "this assertion pass by finding nothing."
    )
    offenders = _offenders(_OPENFOAM_ROOT, exempt=set())
    assert offenders == {}, (
        "omnidriver.openfoam modules resolving an implicit (cardiac) "
        "DriverContext:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nMake driver_context a required parameter instead."
    )
