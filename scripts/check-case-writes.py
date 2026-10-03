#!/usr/bin/env python3
"""Fail when a record, axis or planner module imports or calls a writer.

Only ``commit_case_write`` writes a case. The waiver list is empty; ``if TYPE_CHECKING:`` imports are exempt unless the module rebinds ``TYPE_CHECKING``.
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
# The pure planners axes import, kept separate from the writers; scanned too,
# so an axis can never reach a writer through this module.
PLANNERS_SRC = (
    REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam/case_planning.py"
)
# openCARP's record modules: records address a study key and return a patch.
OPENCARP_RECORDS_SRC = (
    REPO_ROOT / "packages/omnidriver-opencarp/src/omnidriver/opencarp/records"
)
# cardiacCore's record modules: workflow steps and anatomy inputs are pure data.
CARDIACCORE_RECORDS_SRC = (
    REPO_ROOT / "packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/records"
)
SCANNED_ROOTS: tuple[Path, ...] = (
    AXES_SRC, RECORDS_SRC, PLANNERS_SRC, OPENCARP_RECORDS_SRC, CARDIACCORE_RECORDS_SRC,
)

# Importing any name from these modules (or a submodule) is a writer import.
FORBIDDEN_IMPORT_MODULES: tuple[str, ...] = (
    "shutil",
    "subprocess",
    "tempfile",
    "importlib",
    "omnidriver.openfoam.mutators",
    "omnidriver.openfoam.foam_backend",
    # Writer helpers must not live in a module named utils; the pure planners
    # are in case_planning.py, which stays importable.
    "omnidriver.openfoam.utils",
    "omnidriver.core.case_transaction",
    # openCARP's plugin module holds the renderer (patch_par/write); reaching
    # it would be a write path this gate cannot see through.
    "omnidriver.opencarp.plugin",
)

# Forbidden by imported name, whatever module it comes from. `ast.alias.name`
# is the pre-`as` name, so `from os import rename as r` is caught without
# alias resolution.
FORBIDDEN_IMPORT_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
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

# Forbidden by called name (attribute or bare), whatever the receiver:
# `o.rename(...)` matches via the attribute name.
FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset({
    "update_foam_entry",
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

#: A bare reference such as ``wt = Path.write_text`` is as much a writer handle
#: as a call.
FORBIDDEN_ATTRIBUTE_NAMES: frozenset[str] = FORBIDDEN_CALL_NAMES - {
    "__import__", "exec", "eval",
}

#: Override-application helpers are recognised by shape, so one the name list
#: has not met is still refused.
_OVERRIDES_CALL_PATTERN = re.compile(r"^apply_.*overrides?$")


def _runtime_nodes(tree: ast.Module, *, type_checking_shadowed: bool) -> list[ast.stmt | ast.expr]:
    """Statements and expressions reachable at runtime; ``if TYPE_CHECKING:`` bodies are skipped unless the module shadows the name."""
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
    """True if the module assigns to the name ``TYPE_CHECKING``."""
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


def _package_of(path: Path) -> tuple[str, ...]:
    """The dotted package of a source file: the path after the last ``src``, minus the file."""
    parts = path.resolve().parts
    if "src" not in parts:
        return ()
    start = len(parts) - 1 - parts[::-1].index("src") + 1
    return tuple(parts[start:-1])


def _from_module(node: ast.ImportFrom, path: Path) -> str | None:
    """The absolute module an ``ImportFrom`` reads from; a relative import is resolved against the file's package."""
    if node.level == 0:
        return node.module
    package = _package_of(path)
    if node.level - 1 > len(package):
        return node.module
    base = package[: len(package) - (node.level - 1)]
    return ".".join(base + ((node.module,) if node.module else ()))


def _module_names(node: ast.Import | ast.ImportFrom, path: Path) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    module = _from_module(node, path)
    return [] if module is None else [module]


def _imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The pre-``as`` name of each alias, which ``FORBIDDEN_IMPORT_NAMES`` matches."""
    return [alias.name for alias in node.names]


def _open_call_is_a_write(call: ast.Call) -> bool:
    """``open`` with a mode containing w/a/x/+, in builtin or ``Path.open`` form; a non-literal mode counts as a write."""
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
    """Names assigned or ``with``-bound from a ``FoamFile(...)`` call."""
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
    """String-literal arguments to ``getattr(...)``; no other rule sees ``getattr(x, "write_text")``."""
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
            candidate_module_names = list(_module_names(node, path))
            from_module = (
                _from_module(node, path) if isinstance(node, ast.ImportFrom) else None
            )
            if from_module is not None:
                # `from package import submodule` imports `package.submodule`,
                # which `_module_names` alone does not see.
                candidate_module_names.extend(
                    f"{from_module}.{alias.name}" for alias in node.names
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
                receiver = _call_receiver_name(node)
                # Unaliased os/json calls get the `receiver.name` spelling the
                # tests grep for; any other receiver gets the generic message.
                if receiver in {"os", "json"}:
                    message = f"{path}:{node.lineno}: call to {receiver}.{name}(...)"
                else:
                    message = f"{path}:{node.lineno}: call to writer {name!r}(...)"
                violations.append((key, message))
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


# May only shrink; it is empty.
KNOWN_VIOLATIONS: frozenset[str] = frozenset()


def main() -> int:
    found: list[tuple[str, str]] = []
    for scanned_root in SCANNED_ROOTS:
        if scanned_root.is_file():
            found.extend(_check_file(scanned_root, scanned_root.parent))
            continue
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
            "commit_case_write/case_transaction, shutil, "
            "subprocess, tempfile, importlib/__import__, exec/eval, "
            ".write_text(...)/.write_bytes(...), open(..., <write mode>), "
            ".rename/.replace/.remove/.unlink/.symlink/.touch/.mkdir, "
            "json.dump(...), getattr(..., \"write_text\")-style string "
            "attribute access, or a FoamFile item assignment/deletion/"
            ".update(...)/with-block. Axes return patches and command "
            "arguments; only commit_case_write writes a case."
        )
        return 1

    print(
        "Case-write boundaries OK: no writer import or call in "
        "openfoam/axes, cardiacfoam/records, cardiaccore/records, "
        "opencarp/records or openfoam/case_planning.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
