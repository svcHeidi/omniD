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
they're exempt everywhere -- matching ``check-import-boundaries.py`` --
UNLESS the module ALSO rebinds the name ``TYPE_CHECKING`` itself anywhere
(e.g. ``TYPE_CHECKING = True``), in which case the whole file's exemption is
disabled: a locally shadowed sentinel means ``if TYPE_CHECKING:`` is not
``typing.TYPE_CHECKING`` at all, and the gate cannot tell a genuine
type-only import from one hidden behind a look-alike guard, so it treats
none of them as exempt in that file (review finding M2, evasion e23).

**Runtime purity is also enforced mechanically, not only statically**: see
``tutorial_records.resolve_case_patches``, which digests the staged case
before and after every ``axis.resolve`` call and refuses BY NAME if anything
changed. This static gate catches an evasion before it ever runs; that
runtime digest catches whatever this gate's necessarily-incomplete pattern
matching still misses (e.g. an evasion this list has not been taught yet).
"""

from __future__ import annotations

import ast
import re
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
    "subprocess",
    "tempfile",
    "importlib",
    "omnidriver.openfoam.mutators",
    "omnidriver.openfoam.foam_backend",
    # M2 (utils.py split): utils.py now contains ONLY writers (set_delta_t
    # and kin) -- the pure planners moved to case_planning.py, which is not
    # named here and remains importable.
    "omnidriver.openfoam.utils",
    "omnidriver.openfoam.apply_overrides",
    "omnidriver.core.case_transaction",
    "omnidriver.cardiacfoam.overrides",
)

# Forbidden by imported/bound NAME, regardless of which module it came from
# -- a record or axis module must not import these under any alias or path.
# `ast.alias.name` is always the ORIGINAL (pre-`as`) name, so this already
# catches `from os import rename as r` (the bound local name is `r`, but the
# import statement's OWN name is still `rename`) without any alias
# resolution.
FORBIDDEN_IMPORT_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
    "apply_electro_property_overrides",
    "apply_physics_property_overrides",
    "apply_overrides",
    "apply_case_overrides",
    "commit_case_write",
    "case_transaction",
    "dump",
    "write_text",
    "write_bytes",
    "rename",
    "replace",
    "remove",
    "unlink",
    "symlink",
    "touch",
    "mkdir",
})

# Forbidden by CALLED name (attribute or bare), regardless of receiver --
# within this narrowly-scoped axes/records directory there is no legitimate
# reason to call any of these, aliased or not: `o.rename(...)` matches via
# the Attribute's own `.attr`, no alias resolution needed either.
FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
    "apply_electro_property_overrides",
    "apply_physics_property_overrides",
    "apply_overrides",
    "apply_case_overrides",
    "commit_case_write",
    "write_text",
    "write_bytes",
    "rename",
    "replace",
    "remove",
    "unlink",
    "symlink",
    "touch",
    "mkdir",
    "dump",
    "__import__",
    "exec",
    "eval",
})

#: Standalone references to one of these attributes (never called at all,
#: e.g. ``wt = Path.write_text``) are just as much a writer handle as
#: calling it directly -- evasion e02.
FORBIDDEN_ATTRIBUTE_NAMES: frozenset[str] = FORBIDDEN_CALL_NAMES - {
    "__import__", "exec", "eval",
}

#: A call whose called-name matches this pattern is an override-application
#: helper by shape, regardless of which module declares it (generalizes the
#: exact names above to survive a not-yet-seen helper with the same shape).
_OVERRIDES_CALL_PATTERN = re.compile(r"^apply_.*overrides?$")


def _runtime_nodes(tree: ast.Module, *, type_checking_shadowed: bool) -> list[ast.stmt | ast.expr]:
    """All statements/expressions reachable at runtime.

    Skips ``if TYPE_CHECKING:`` bodies UNLESS ``type_checking_shadowed`` --
    see the module docstring's note on evasion e23.
    """
    found: list[ast.stmt | ast.expr] = []

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            test = node.test
            is_type_checking = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_type_checking and not type_checking_shadowed:
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


def _type_checking_is_shadowed(tree: ast.Module) -> bool:
    """True if the module ever assigns to a name literally called
    ``TYPE_CHECKING`` -- genuine ``typing.TYPE_CHECKING`` usage never
    rebinds that name, so any assignment to it means whatever ``if
    TYPE_CHECKING:`` appears in this file cannot be trusted to mean the real
    sentinel (evasion e23)."""
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "TYPE_CHECKING":
                return True
    return False


def _module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.module is None:
        return []
    return [node.module]


def _imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The name each alias in this import statement was ORIGINALLY bound to
    (never the local ``as`` rename) -- what ``FORBIDDEN_IMPORT_NAMES``
    matches against, so ``from os import rename as r`` is still caught by
    the import line itself even though the call site only ever says ``r``."""
    return [alias.name for alias in node.names]


def _open_call_is_a_write(call: ast.Call) -> bool:
    """``open(..., "w"...)`` and kin -- a mode containing w/a/x/+.

    Handles both the builtin's shape (``open(file, mode)``, mode at
    positional index 1) and a bound method's (``some_path.open(mode)``,
    mode at positional index 0 since there is no separate ``file`` argument)
    -- the builtin-only indexing used to let ``Path(...).open("w")`` evade
    entirely (evasion e09).

    A non-literal (dynamic) mode cannot be proven read-only, so it is
    treated as a write too: this gate has an empty waiver list, and "I
    cannot tell" is not a reason to let a write through it.
    """
    is_method_form = isinstance(call.func, ast.Attribute)
    mode_index = 0 if is_method_form else 1
    mode_node: ast.expr | None = None
    if len(call.args) > mode_index:
        mode_node = call.args[mode_index]
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
    """Local names assigned or ``with``-bound from a call to (something
    ending in) ``FoamFile`` -- e.g. ``x = FoamFile(...)`` or ``with
    FoamFile(...) as x:`` (evasion e15's shape, the latter was not
    recognized at all before)."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_func_name(node.value) == "FoamFile":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)
        elif isinstance(node, ast.With):
            for item in node.items:
                if (
                    isinstance(item.context_expr, ast.Call)
                    and _call_func_name(item.context_expr) == "FoamFile"
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    bound.add(item.optional_vars.id)
    return bound


def _subscript_base_text(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _is_foam_file_receiver(receiver_text: str, foam_file_names: set[str]) -> bool:
    return "FoamFile" in receiver_text or any(
        receiver_text == name or receiver_text.startswith(name + ".")
        for name in foam_file_names
    )


def _getattr_string_args(call: ast.Call) -> list[str]:
    """String-literal arguments to a bare ``getattr(...)`` call -- catches
    ``getattr(x, "write_text")(...)`` (evasion e03): the attribute name is
    never a Python identifier in the source, so no other rule sees it."""
    if _call_func_name(call) != "getattr" or isinstance(call.func, ast.Attribute):
        return []
    literals: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            literals.append(arg.value)
    for keyword in call.keywords:
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                literals.append(keyword.value.value)
    return literals


def _check_file(path: Path, root: Path) -> list[tuple[str, str]]:
    """Return (waiver_key, human_message) for each forbidden write form."""
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    violations: list[tuple[str, str]] = []
    foam_file_names = _foam_file_bound_names(tree)
    type_checking_shadowed = _type_checking_is_shadowed(tree)

    for node in _runtime_nodes(tree, type_checking_shadowed=type_checking_shadowed):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            candidate_module_names = list(_module_names(node))
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                # `from package import submodule` really imports the
                # dotted name `package.submodule` -- `_module_names` alone
                # only sees the "from" half (`package`), which misses this
                # shape entirely (evasion e26: `from omnidriver.openfoam
                # import utils` naming a forbidden SUBMODULE this way).
                candidate_module_names.extend(
                    f"{node.module}.{alias.name}" for alias in node.names
                )
            for module_name in candidate_module_names:
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

        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTE_NAMES:
                key = f"{path.relative_to(root)}:{node.lineno}:attr:{node.attr}"
                violations.append((
                    key,
                    f"{path}:{node.lineno}: reference to writer attribute "
                    f".{node.attr} (not necessarily called here, but a handle "
                    "to one)",
                ))
            continue

        if isinstance(node, ast.Call):
            name = _call_func_name(node)
            for literal in _getattr_string_args(node):
                if literal in FORBIDDEN_ATTRIBUTE_NAMES:
                    key = f"{path.relative_to(root)}:{node.lineno}:getattr-string:{literal}"
                    violations.append((
                        key,
                        f"{path}:{node.lineno}: getattr(..., {literal!r}) -- a "
                        "string-attribute reference to a writer",
                    ))
            if name in FORBIDDEN_CALL_NAMES:
                key = f"{path.relative_to(root)}:{node.lineno}:call:{name}"
                violations.append((
                    key, f"{path}:{node.lineno}: call to writer {name!r}(...)",
                ))
            elif name is not None and _OVERRIDES_CALL_PATTERN.match(name):
                key = f"{path.relative_to(root)}:{node.lineno}:call:{name}"
                violations.append((
                    key, f"{path}:{node.lineno}: call to override-applying "
                    f"writer {name!r}(...)",
                ))
            elif name == "open" and _open_call_is_a_write(node):
                key = f"{path.relative_to(root)}:{node.lineno}:call:open-write"
                violations.append((
                    key, f"{path}:{node.lineno}: open(...)/.open(...) with a "
                    "write/append mode",
                ))
            elif (
                name == "update"
                and isinstance(node.func, ast.Attribute)
                and (
                    (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id in foam_file_names
                    )
                    or (
                        isinstance(node.func.value, ast.Call)
                        and _call_func_name(node.func.value) == "FoamFile"
                    )
                )
            ):
                key = f"{path.relative_to(root)}:{node.lineno}:call:foamfile-update"
                violations.append((
                    key, f"{path}:{node.lineno}: FoamFile(...).update(...)",
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
                if _is_foam_file_receiver(base_text, foam_file_names):
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
            "omnidriver.openfoam.mutators/foam_backend/utils, "
            "apply_electro_property_overrides/apply_physics_property_overrides/"
            "apply_*_overrides, commit_case_write/case_transaction, shutil, "
            "subprocess, tempfile, importlib/__import__, exec/eval, "
            ".write_text(...)/.write_bytes(...), open(..., <write mode>), "
            ".rename/.replace/.remove/.unlink/.symlink/.touch/.mkdir, "
            "json.dump(...), getattr(..., \"write_text\")-style string "
            "attribute access, or a FoamFile item assignment/deletion/"
            ".update(...)/with-block. Axes return patches and command "
            "arguments; only commit_case_write writes a case. See design doc "
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
