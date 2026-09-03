#!/usr/bin/env python3
"""Enforce ARCHITECTURE.md's package-independence rules as a CI gate.

Rules (see ARCHITECTURE.md "Architectural Rules"):
  1. omnidriver.core must not import omnidriver.openfoam or omnidriver.cardiacfoam,
     and must never import foamlib directly.
  2. omnidriver.openfoam must not import omnidriver.cardiacfoam.

core/compatibility.py is exempt from the omnidriver.openfoam prefix only: its
ungated environment fallbacks are a documented, overridable default (see
future/ENVIRONMENT_CONTRACT.md §4) -- those imports are never reached unless a
plugin declines to implement the corresponding capability hook.
compatibility.py is NOT exempt from the omnidriver.cardiacfoam prefix, and no
longer needs to be: it contains no cardiac import at all. Any cardiac import
appearing anywhere in core now fails this gate outright, with no waiver to
add it to. compatibility.py may still not import foamlib directly; it must go
through omnidriver.openfoam.

Imports inside ``if TYPE_CHECKING:`` blocks are never runtime imports, so
they're exempt everywhere.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The WHOLE core package, not just its core/ subdirectory. Scanning only
# core/ left packages/omnidriver/src/omnidriver/*.py unchecked -- which is
# exactly where the worst violation lives: cli.py hard-imports
# omnidriver.openfoam at module scope, so `import omnidriver.cli` raises
# ModuleNotFoundError in the core-only install this project's test-core CI job
# claims to verify. This gate reported "boundaries OK" throughout.
CORE_SRC = REPO_ROOT / "packages/omnidriver/src/omnidriver"
OPENFOAM_SRC = REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam"
COMPATIBILITY_FILE = CORE_SRC / "core" / "compatibility.py"

# Waived pre-existing violations. This list may only SHRINK. A new violation
# fails the gate; a waiver that no longer matches anything also fails it, so
# the list cannot rot into a lie the way the old narrow scope did.
#
# It is now EMPTY, which is the point: core contains no runtime cardiac import
# at all, so this gate no longer records exceptions to its own rule -- it
# asserts the rule outright.
#
# The last two entries were core/compatibility.py's
# legacy_default_driver_context and legacy_generic_case_mutation, both of the
# same shape: the historical public API lets a caller omit a plugin/context
# entirely, and core answered by importing cardiacFoam. Both were described
# here as "permanent compatibility edge (not debt)". They were not permanent.
# The public no-argument API survives unchanged; what changed is that the
# default now resolves through the omnidriver.plugins entry-point group, and
# the cardiac dictionary vocabulary moved to the plugin that means it. See
# docs/superpowers/specs/2026-09-02-neutral-default-context-design.md.
KNOWN_VIOLATIONS: frozenset[str] = frozenset()
# Removed once fixed: cli.py's two module-scope omnidriver.openfoam imports,
# which made `import omnidriver.cli` fail in a core-only install. They now go
# through EnvironmentPreflightCapability.load and OverrideScopeCapability.apply.


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


def _check_file(
    path: Path, forbidden_prefixes: tuple[str, ...], root: Path,
) -> list[tuple[str, str]]:
    """Return (waiver_key, human_message) for each forbidden runtime import."""
    tree = ast.parse(path.read_text(), filename=str(path))
    violations = []
    for node in _runtime_import_nodes(tree):
        for name in _module_name(node):
            if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes):
                key = f"{path.relative_to(root)}:{node.lineno}:{name}"
                violations.append(
                    (key, f"{path}:{node.lineno}: runtime import of {name!r}")
                )
    return violations


def main() -> int:
    found: list[tuple[str, str]] = []

    for path in CORE_SRC.rglob("*.py"):
        if path == COMPATIBILITY_FILE:
            # Still exempt for omnidriver.openfoam: the ungated environment
            # fallbacks are a documented, overridable default
            # (future/ENVIRONMENT_CONTRACT.md §4). NOT exempt for
            # omnidriver.cardiacfoam any more -- after Task 7 the only cardiac
            # imports left serve the public compatibility edge, and any new one
            # is a regression.
            forbidden = ("foamlib", "omnidriver.cardiacfoam")
        else:
            forbidden = ("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam")
        found.extend(_check_file(path, forbidden, CORE_SRC))

    for path in OPENFOAM_SRC.rglob("*.py"):
        found.extend(_check_file(path, ("omnidriver.cardiacfoam",), OPENFOAM_SRC))

    waived = {key for key, _ in found if key in KNOWN_VIOLATIONS}
    violations = [msg for key, msg in found if key not in KNOWN_VIOLATIONS]

    # A waiver matching nothing means the violation was fixed (good) or moved
    # (bad) -- either way the list is out of date and must be corrected, or it
    # decays into the same false reassurance the narrow scope gave for months.
    stale = sorted(KNOWN_VIOLATIONS - waived)
    if stale:
        print("Stale entries in KNOWN_VIOLATIONS -- these no longer match anything:\n")
        for key in stale:
            print(f"  {key}")
        print(
            "\nIf you fixed them, delete them from KNOWN_VIOLATIONS in this script. "
            "The list may only shrink."
        )
        return 1

    if waived:
        print(f"{len(waived)} known violation(s) waived (see KNOWN_VIOLATIONS):")
        for key in sorted(waived):
            print(f"  {key}")
        print()

    if violations:
        print("Import boundary violations found:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nomnidriver.core must not import foamlib or omnidriver.cardiacfoam at "
            "runtime, and must not import omnidriver.openfoam except inside "
            "core/compatibility.py's ungated environment fallbacks (a documented, "
            "overridable default -- see future/ENVIRONMENT_CONTRACT.md §4). "
            "omnidriver.openfoam must not import omnidriver.cardiacfoam. "
            "See ARCHITECTURE.md's Architectural Rules."
        )
        return 1

    if waived:
        print(
            "Import boundaries OK apart from the waived entries above: no NEW "
            "coupling between core, openfoam and cardiac."
        )
    else:
        print("Import boundaries OK: core/openfoam/cardiac stay decoupled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
