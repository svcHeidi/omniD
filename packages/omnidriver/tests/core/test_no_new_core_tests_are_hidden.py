"""A module-level ``importorskip`` in core's tree hides a whole file from collection, not merely skips it."""
from __future__ import annotations

import ast
import pathlib

_CORE_TESTS = pathlib.Path(__file__).resolve().parent.parent

#: Core test files that skip wholesale without a sibling package, with the
#: number of tests each removes from core's suite. Shrink-only.
KNOWN_HIDDEN_FILES: dict[str, int] = {}


def _module_level_importorskip(path: pathlib.Path) -> bool:
    """True when the file calls ``pytest.importorskip`` at module scope."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        # Descending into a def/class would flag a function-level
        # importorskip, which skips ONE test and still collects the rest --
        # correct usage, and not what this guards.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "importorskip":
                return True
    return False


def _hidden_files() -> set[str]:
    found = set()
    for path in sorted(_CORE_TESTS.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        if _module_level_importorskip(path):
            found.add(path.relative_to(_CORE_TESTS).as_posix())
    return found


def test_no_new_core_test_file_is_hidden_wholesale() -> None:
    unexpected = sorted(_hidden_files() - set(KNOWN_HIDDEN_FILES))
    assert unexpected == [], (
        "core test files newly skipped wholesale by a module-level "
        "importorskip:\n" + "\n".join(f"  {f}" for f in unexpected)
        + "\n\nA file that cannot run without a sibling package is a test of "
        "that sibling. Move it to that package's tests/ tree rather than "
        "hiding it here -- skipping keeps core's suite green while making it "
        "measure less."
    )


def test_the_hidden_list_has_not_gone_stale() -> None:
    """A listed file that no longer hides is progress; delete its entry."""
    stale = sorted(set(KNOWN_HIDDEN_FILES) - _hidden_files())
    assert stale == [], (
        "these files no longer skip wholesale -- remove them from "
        "KNOWN_HIDDEN_FILES:\n" + "\n".join(f"  {f}" for f in stale)
    )
