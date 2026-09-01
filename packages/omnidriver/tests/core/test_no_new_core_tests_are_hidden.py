"""A module-level ``importorskip`` in core's tree hides a whole file.

Task 5a converted core to require an explicit ``DriverContext``. Four core test
files turned out to be inherently cardiac -- they exercise cardiacFoam's
tutorial catalogue, not core behaviour -- and were given a module-level
``pytest.importorskip("omnidriver.cardiacfoam...")`` so they skip cleanly in a
core-only install instead of failing.

That is defensible as an interim step and misleading as an end state. A
module-level ``importorskip`` is reported by pytest as **one** skip, and the
file's tests are never collected at all: core's collected count fell 760 -> 725
while the headline failure count fell 140 -> 87. Roughly two thirds of that
improvement is tests leaving the suite, not tests passing.

The failure mode this guards is precise. Nothing is red, nothing is obviously
wrong, and core's suite quietly measures less than it did -- which is the same
class of false reassurance this repository has produced four times already: an
import gate scanning only ``core/``, a collection check blind to function-scoped
imports, a wheel guard reading a stale ``build/lib``, and discovery tests
mocking the very seam that hid the entry-point bug.

So the list below is **shrink-only**, exactly like
``scripts/check-import-boundaries.py``'s ``KNOWN_VIOLATIONS`` and
``test_wheel_install_imports.py``'s ``KNOWN_UNIMPORTABLE``. A new hidden file
fails this test. A listed file that stops matching also fails it, so the list
cannot rot into a lie once Task 5b relocates these to
``packages/omnidriver-cardiacfoam/tests/``, where they belong and where they
run.
"""
from __future__ import annotations

import ast
import pathlib

_CORE_TESTS = pathlib.Path(__file__).resolve().parent.parent

#: Core test files that skip wholesale without a sibling package, with the
#: number of tests each removes from core's suite. Task 5b relocates them;
#: this list may only shrink.
KNOWN_HIDDEN_FILES: dict[str, int] = {
    "core/test_sweep_runner.py": 24,
}


def _module_level_importorskip(path: pathlib.Path) -> bool:
    """True when the file calls ``pytest.importorskip`` at module scope.

    Module scope is the whole point: the same call inside a test function skips
    one test and still collects the rest, which is correct and not what this
    guards.
    """
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
    """A listed file that no longer hides is progress; delete its entry.

    Without this the list would silently outlive the problem, which is how the
    import gate's own waiver list nearly rotted.
    """
    stale = sorted(set(KNOWN_HIDDEN_FILES) - _hidden_files())
    assert stale == [], (
        "these files no longer skip wholesale -- remove them from "
        "KNOWN_HIDDEN_FILES:\n" + "\n".join(f"  {f}" for f in stale)
    )
