#!/usr/bin/env python3
"""Fail when a package imports across the layering ARCHITECTURE.md forbids; ``if TYPE_CHECKING:`` imports are exempt.

Core imports no adapter nor foamlib; openfoam no cardiac adapter; opencarp no other adapter nor foamlib, and none imports opencarp.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The whole core package, not only core/: top-level modules such as cli.py
# must import cleanly in a core-only install too.
CORE_SRC = REPO_ROOT / "packages/omnidriver/src/omnidriver"
OPENFOAM_SRC = REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam"
# The two cardiac adapters are siblings: a direct import would make one
# adapter's vocabulary a silent dependency of the other, so the seam between
# them is declared, not imported.
CARDIACCORE_SRC = REPO_ROOT / "packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore"
# openCARP drives a different binary: no OpenFOAM, cardiac or foamlib import
# belongs in it.
OPENCARP_SRC = REPO_ROOT / "packages/omnidriver-opencarp/src/omnidriver/opencarp"
CARDIACFOAM_SRC = REPO_ROOT / "packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam"


def _adapter_package_roots() -> dict[str, Path]:
    """Every adapter's ``omnidriver.<name>`` package, found on disk outside core's distribution."""
    core_dist = CORE_SRC.parent.parent
    return {
        f"omnidriver.{init.parent.name}": init.parent
        for init in sorted(REPO_ROOT.glob("packages/*/src/omnidriver/*/__init__.py"))
        if init.parent.parent.parent.parent != core_dist
    }

# Waived violations; the list is empty and may only shrink. A waiver that
# matches nothing fails the gate, so it cannot rot into a stale exemption.
KNOWN_VIOLATIONS: frozenset[str] = frozenset()


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
    adapters = _adapter_package_roots()

    # Each adapter's own rules. Every adapter found on disk must appear here;
    # one that does not is refused below rather than silently exempted.
    adapter_rules: dict[Path, tuple[str, ...]] = {
        OPENFOAM_SRC: ("omnidriver.cardiacfoam", "omnidriver.cardiaccore", "omnidriver.opencarp"),
        CARDIACFOAM_SRC: ("omnidriver.opencarp",),
        CARDIACCORE_SRC: ("omnidriver.cardiacfoam", "omnidriver.opencarp"),
        OPENCARP_SRC: ("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam", "omnidriver.cardiaccore"),
    }
    unruled = sorted(name for name, root in adapters.items() if root not in adapter_rules)
    if unruled:
        print(
            "Adapter packages with no import-boundary block in this script: "
            + ", ".join(unruled)
            + "\nAdd a block to adapter_rules in main() stating what each may not import."
        )
        return 1

    # Core may import no adapter at all, and never foamlib (derived).
    core_forbidden = ("foamlib", *sorted(adapters))
    for path in CORE_SRC.rglob("*.py"):
        found.extend(_check_file(path, core_forbidden, CORE_SRC))

    for root, forbidden in adapter_rules.items():
        for path in root.rglob("*.py"):
            found.extend(_check_file(path, forbidden, root))

    waived = {key for key, _ in found if key in KNOWN_VIOLATIONS}
    violations = [msg for key, msg in found if key not in KNOWN_VIOLATIONS]

    # A waiver matching nothing means the violation was fixed or moved; either
    # way the list is out of date.
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
            "\nomnidriver.core must not import foamlib or any adapter package "
            "at runtime. omnidriver.openfoam must not import either cardiac "
            "package or omnidriver.opencarp; no adapter imports "
            "omnidriver.opencarp, and it imports no other adapter. "
            "omnidriver.cardiaccore must not "
            "import omnidriver.cardiacfoam: the two cardiac adapters are "
            "siblings, and what passes between them is declared, not imported. "
            "A cardiac adapter importing omnidriver.openfoam is allowed -- that "
            "is the direction the layering permits. "
            "See ARCHITECTURE.md's Architectural Rules."
        )
        return 1

    if waived:
        print(
            "Import boundaries OK apart from the waived entries above: no NEW "
            "coupling between core, openfoam and cardiac."
        )
    else:
        print("Import boundaries OK: core and every adapter stay decoupled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
