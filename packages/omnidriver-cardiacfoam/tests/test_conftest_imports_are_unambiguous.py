"""`from conftest import X` in this tree must resolve to a name core also has.

When the whole repository is collected, both packages' ``tests`` directories
are reachable and **core's conftest wins** -- so a cardiac test doing
``from conftest import monorepo_root`` gets *core's* ``monorepo_root``, not the
one beside it. That works today only because core's conftest happens to define
the same names.

The failure mode is silent until it is not: adding a cardiac-only helper to
this package's conftest and importing it that way passes when the package is
run alone and raises ImportError in a full-repo run. That happened on
2026-09-04 and cost three attempts to place one helper.

This makes it fail immediately instead. A package-specific helper belongs in a
uniquely named module inside an importable package -- see
``regression_equivalence/tutorials_tree.py``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_CARDIAC_TESTS = Path(__file__).resolve().parent
# packages/omnidriver-cardiacfoam/tests -> packages -> omnidriver/tests
_CORE_CONFTEST = _CARDIAC_TESTS.parents[1] / "omnidriver" / "tests" / "conftest.py"


def _names_defined_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return names


def test_core_conftest_is_where_this_guard_thinks_it_is() -> None:
    """A guard that resolved to nothing would pass by scanning zero names."""
    assert _CORE_CONFTEST.is_file(), (
        f"expected core's conftest at {_CORE_CONFTEST}; fix the path rather "
        "than letting this guard pass by finding nothing."
    )


def test_every_conftest_import_here_also_exists_in_cores() -> None:
    core_names = _names_defined_in(_CORE_CONFTEST)
    assert core_names, "core's conftest parsed to zero names"

    pattern = re.compile(r"^\s*from conftest import ([^\n(]+)$", re.MULTILINE)
    offenders: list[str] = []
    for path in sorted(_CARDIAC_TESTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for match in pattern.finditer(path.read_text()):
            for raw in match.group(1).split(","):
                name = raw.strip().split(" as ")[0].strip()
                if name and name not in core_names:
                    offenders.append(
                        f"{path.relative_to(_CARDIAC_TESTS)}: {name}"
                    )

    assert offenders == [], (
        "these `from conftest import ...` names do not exist in CORE's "
        "conftest, which is the one that wins in a full-repo run:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\nPut package-specific helpers in a uniquely named module inside an "
        "importable package instead (e.g. regression_equivalence/tutorials_tree.py)."
    )
