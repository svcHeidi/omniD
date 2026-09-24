#!/usr/bin/env python3
"""Enforce design §5's "records and axes write nothing" rule as a CI gate.

docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md §5:

  A static gate, like ``scripts/check-import-boundaries.py``, with an empty
  waiver list: tutorial registrations and axis modules may not import or
  call a writer (``update_foam_entry``, ``apply_*_overrides``, ``shutil``,
  ``write_text``, ``open(..., "w")``). Axes return patches and command
  arguments; only ``commit_case_write`` writes a case.

This scans EXACTLY the two directories where records and axes live --
nowhere else. Both are new and empty apart from ``__init__.py`` as of this
gate's introduction; every tutorial-record axis (OpenFOAM's generic ones,
cardiacFOAM's solver-specific ones) and every cardiacFOAM tutorial-record
registration lands under one of these two trees, by construction (design
§3's package table), never elsewhere.

Like ``check-import-boundaries.py``, this list may only SHRINK -- and here
it starts, and stays, empty. If you find yourself wanting to add a waiver,
the fix is to route the write through ``commit_case_write`` instead, not to
waive this gate (CLAUDE.md: "If you find yourself wanting to add a waiver,
you are solving the wrong problem").

Imports inside ``if TYPE_CHECKING:`` blocks are never runtime imports, so
they're exempt everywhere -- matching ``check-import-boundaries.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

AXES_SRC = (
    REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam/axes"
)
RECORDS_SRC = (
    REPO_ROOT / "packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records"
)
SCANNED_ROOTS: tuple[Path, ...] = (AXES_SRC, RECORDS_SRC)

# Forbidden by full or partial dotted module name: importing ANY name from
# these modules is a writer import, regardless of which name is imported
# ("anything from openfoam mutators/foam_backend").
FORBIDDEN_IMPORT_MODULES: tuple[str, ...] = (
    "shutil",
    "omnidriver.openfoam.mutators",
    "omnidriver.openfoam.foam_backend",
)

# Forbidden by imported/bound NAME, regardless of which module it came from
# -- a record or axis module must not import these under any alias or path.
FORBIDDEN_IMPORT_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
    "apply_electro_property_overrides",
    "apply_physics_property_overrides",
})

# Forbidden by CALLED name (attribute or bare) -- catches a qualified call
# through a module import that the two rules above did not already refuse
# (e.g. `import omnidriver.openfoam.mutators as m; m.update_foam_entry(...)`
# would already be caught by FORBIDDEN_IMPORT_MODULES, but this also catches
# the same names reached via a different, permitted import path).
FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
    "apply_electro_property_overrides",
    "apply_physics_property_overrides",
    "write_text",
    "write_bytes",
})

# `os.replace`/`os.rename`, `json.dump` -- matched as Attribute calls on a
# bare `os`/`json` name (design's own literal spelling).
_OS_WRITE_ATTRS: frozenset[str] = frozenset({"replace", "rename"})


def _runtime_nodes(tree: ast.Module) -> list[ast.stmt | ast.expr]:
    """All statements/expressions reachable at runtime (skips TYPE_CHECKING)."""
    found: list[ast.stmt | ast.expr] = []

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

        def generic_visit(self, node: ast.AST) -> None:
            if isinstance(node, (ast.stmt, ast.expr)):
                found.append(node)
            super().generic_visit(node)

    Visitor().visit(tree)
    return found


def _module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.module is None:
        return []
    return [node.module]


def _imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The names this import binds locally (the alias if renamed, else the
    original name) -- what ``FORBIDDEN_IMPORT_NAMES`` matches against."""
    return [alias.name for alias in node.names]


def _open_call_is_a_write(call: ast.Call) -> bool:
    """``open(..., "w"...)`` and kin -- a mode containing w/a/x/+.

    A non-literal (dynamic) mode cannot be proven read-only, so it is
    treated as a write too: this gate has an empty waiver list, and "I
    cannot tell" is not a reason to let a write through it.
    """
    mode_node: ast.expr | None = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
    if mode_node is None:
        return False  # default mode is "r"
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        mode = mode_node.value
        return any(flag in mode for flag in ("w", "a", "x", "+"))
    return True  # non-literal mode: cannot prove it is read-only


def _call_func_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _call_receiver_name(call: ast.Call) -> str | None:
    """For an Attribute call ``recv.attr(...)``, the bare name of ``recv``."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return None


def _foam_file_bound_names(tree: ast.Module) -> set[str]:
    """Local names assigned from a call to (something ending in) ``FoamFile``."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        called = _call_func_name(node.value)
        if called != "FoamFile":
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bound.add(target.id)
    return bound


def _subscript_base_text(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _check_file(path: Path, root: Path) -> list[tuple[str, str]]:
    """Return (waiver_key, human_message) for each forbidden write form."""
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    violations: list[tuple[str, str]] = []
    foam_file_names = _foam_file_bound_names(tree)

    for node in _runtime_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module_name in _module_names(node):
                if any(
                    module_name == prefix or module_name.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_MODULES
                ):
                    key = f"{path.relative_to(root)}:{node.lineno}:import:{module_name}"
                    violations.append((
                        key,
                        f"{path}:{node.lineno}: runtime import of {module_name!r} "
                        "(a writer module)",
                    ))
            for imported_name in _imported_names(node):
                if imported_name in FORBIDDEN_IMPORT_NAMES:
                    key = f"{path.relative_to(root)}:{node.lineno}:import-name:{imported_name}"
                    violations.append((
                        key,
                        f"{path}:{node.lineno}: runtime import of writer "
                        f"{imported_name!r}",
                    ))
            continue

        if isinstance(node, ast.Call):
            name = _call_func_name(node)
            if name in FORBIDDEN_CALL_NAMES:
                key = f"{path.relative_to(root)}:{node.lineno}:call:{name}"
                violations.append((
                    key, f"{path}:{node.lineno}: call to writer {name!r}(...)",
                ))
            elif name == "open" and _open_call_is_a_write(node):
                key = f"{path.relative_to(root)}:{node.lineno}:call:open-write"
                violations.append((
                    key, f"{path}:{node.lineno}: open(...) with a write/append mode",
                ))
            elif name in _OS_WRITE_ATTRS and _call_receiver_name(node) == "os":
                key = f"{path.relative_to(root)}:{node.lineno}:call:os.{name}"
                violations.append((
                    key, f"{path}:{node.lineno}: call to os.{name}(...)",
                ))
            elif (
                name == "dump"
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"
            ):
                key = f"{path.relative_to(root)}:{node.lineno}:call:json.dump"
                violations.append((
                    key, f"{path}:{node.lineno}: call to json.dump(...)",
                ))
            continue

        if isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
            targets: list[ast.expr]
            if isinstance(node, ast.Delete):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            else:
                targets = list(node.targets)
            for target in targets:
                if not isinstance(target, ast.Subscript):
                    continue
                base_text = _subscript_base_text(target.value)
                is_foam_file = (
                    "FoamFile" in base_text
                    or any(
                        base_text == name or base_text.startswith(name + ".")
                        for name in foam_file_names
                    )
                )
                if is_foam_file:
                    verb = "deletion" if isinstance(node, ast.Delete) else "assignment"
                    key = f"{path.relative_to(root)}:{target.lineno}:foamfile-item-{verb}"
                    violations.append((
                        key,
                        f"{path}:{target.lineno}: FoamFile item {verb} "
                        f"({base_text}[...])",
                    ))

    return violations


# May only SHRINK, and starts (and stays) empty -- see the module docstring.
KNOWN_VIOLATIONS: frozenset[str] = frozenset()


def main() -> int:
    found: list[tuple[str, str]] = []
    for scanned_root in SCANNED_ROOTS:
        if not scanned_root.is_dir():
            print(f"error: scanned root does not exist: {scanned_root}")
            return 1
        for path in sorted(scanned_root.rglob("*.py")):
            found.extend(_check_file(path, scanned_root))

    waived = {key for key, _ in found if key in KNOWN_VIOLATIONS}
    violations = [msg for key, msg in found if key not in KNOWN_VIOLATIONS]

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

    if violations:
        print("Case-write boundary violations found in records/axes modules:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nA tutorial-record registration or an axis module may not import or "
            "call a writer -- update_foam_entry, anything from "
            "omnidriver.openfoam.mutators/foam_backend, "
            "apply_electro_property_overrides/apply_physics_property_overrides, "
            "shutil, .write_text(...)/.write_bytes(...), open(..., <write mode>), "
            "os.replace/os.rename, json.dump(...), or a FoamFile item "
            "assignment/deletion. Axes return patches and command arguments; only "
            "commit_case_write writes a case. See design doc "
            "docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md §5."
        )
        return 1

    print(
        "Case-write boundaries OK: no writer import or call in "
        "openfoam/axes or cardiacfoam/records."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
