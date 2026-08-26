#!/usr/bin/env python3
"""Enforce ARCHITECTURE.md's package-independence rules as a CI gate.

Rules (see ARCHITECTURE.md "Architectural Rules"):
  1. omnidriver.core must not import omnidriver.openfoam or omnidriver.cardiacfoam,
     and must never import foamlib directly.
  2. omnidriver.openfoam must not import omnidriver.cardiacfoam.

The one documented exception is core/compatibility.py, whose whole purpose is
lazily importing omnidriver.openfoam/omnidriver.cardiacfoam inside legacy_*
fallback functions (see docs/superpowers/plans/2026-08-25-monorepo-package-migration.md
Task 5 Step 3) -- those imports are never reached unless a plugin declines to
implement the corresponding capability hook. compatibility.py may still not
import foamlib directly; it must go through omnidriver.openfoam.

Imports inside ``if TYPE_CHECKING:`` blocks are never runtime imports, so
they're exempt everywhere.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CORE_SRC = REPO_ROOT / "packages/omnidriver/src/omnidriver/core"
OPENFOAM_SRC = REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam"
COMPATIBILITY_FILE = CORE_SRC / "compatibility.py"


def _module_name(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.module is None:
        return []
    return [node.module]


def _runtime_import_nodes(tree: ast.Module) -> list[ast.Import | ast.ImportFrom]:
    """All Import/ImportFrom nodes reachable at runtime (skips TYPE_CHECKING bodies)."""
    found: list[ast.Import | ast.ImportFrom] = []

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            test = node.test
            is_type_checking = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_type_checking:
                for stmt in node.orelse:
                    self.visit(stmt)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            found.append(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            found.append(node)

    Visitor().visit(tree)
    return found


def _check_file(path: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations = []
    for node in _runtime_import_nodes(tree):
        for name in _module_name(node):
            if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes):
                violations.append(f"{path}:{node.lineno}: runtime import of {name!r}")
    return violations


def main() -> int:
    violations: list[str] = []

    for path in CORE_SRC.rglob("*.py"):
        if path == COMPATIBILITY_FILE:
            forbidden = ("foamlib",)
        else:
            forbidden = ("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam")
        violations.extend(_check_file(path, forbidden))

    for path in OPENFOAM_SRC.rglob("*.py"):
        violations.extend(_check_file(path, ("omnidriver.cardiacfoam",)))

    if violations:
        print("Import boundary violations found:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nomnidriver.core must not import foamlib, omnidriver.openfoam, or "
            "omnidriver.cardiacfoam at runtime (except inside core/compatibility.py's "
            "legacy_* fallbacks, which may import omnidriver.openfoam/omnidriver.cardiacfoam "
            "but never foamlib directly). omnidriver.openfoam must not import "
            "omnidriver.cardiacfoam. See ARCHITECTURE.md's Architectural Rules."
        )
        return 1

    print("Import boundaries OK: core/openfoam/cardiac stay decoupled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
