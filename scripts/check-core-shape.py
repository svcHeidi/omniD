#!/usr/bin/env python3
"""Fail when core names OpenFOAM layout tokens beyond the recorded baseline, scripts/core-shape-baseline.txt.

Tokens are counted per (file, token) in identifiers and string literals; a new, higher or shrunk count fails.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = REPO_ROOT / "packages/omnidriver/src/omnidriver"
BASELINE = REPO_ROOT / "scripts/core-shape-baseline.txt"
TOKENS = (
    "controlDict", "fvSchemes", "fvSolution", "polyMesh", "blockMesh", "decomposePar",
    "reconstructPar", "processor", "case.foam", "Allrun", "Allclean", "bashrc",
    "WM_PROJECT", "FOAM_", "foamlib",
    # Time-indexed vocabulary (start time, the {time} path placeholder) that
    # core must not grow.
    "start_time", "startTime", "latestTime", "time_indexed", "{time}",
    # Plan-report concepts owned by one solver family's ``get_plan_diagnostics``.
    "function_object", "nondimensional", "dictionary_resolution",
)

# Matching is casefolded with these separators stripped from both token and
# text, so ``touch_case_foam`` counts as ``case.foam``.
_SEPARATORS = str.maketrans("", "", "_.-")

# `processor` must not be preceded by a letter, so postprocessor/preprocessor
# are excluded but processor_dir (separator already stripped) is not.
_PROCESSOR_RE = re.compile(r"(?<![a-z])processor")

TODO_REASON = "TODO-reason"

_DEFAULT_HEADER = (
    "# Recorded OpenFOAM-layout debt in core. Format:\n"
    "# <path relative to core src>\\t<token>\\t<count>\\t<reason>\n"
    "# This is debt, not a waiver: scripts/check-core-shape.py fails on any new\n"
    "# (file, token) pair, any higher count, and any count that shrank without\n"
    "# this file being edited to match -- so the total can only go down.\n"
)


def _normalize(text: str) -> str:
    return text.translate(_SEPARATORS).casefold()


def _count_token(token: str, raw_text: str, normalized_text: str) -> int:
    if token == "FOAM_":
        # Exact and unbounded so it also catches OPENFOAM_*, itself real coupling.
        return raw_text.count("FOAM_")
    if token == "processor":
        return len(_PROCESSOR_RE.findall(normalized_text))
    return normalized_text.count(_normalize(token))


def _is_string_expr_statement(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Ids of bare string statements in any body: docstrings and attribute docstrings are prose, not coupling."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in getattr(node, "body", []):
                if _is_string_expr_statement(stmt):
                    ids.add(id(stmt.value))
    return ids


def _texts(tree: ast.AST):
    skip = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.value
        elif isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name


def count(core_src: Path) -> Counter:
    counts: Counter = Counter()
    for path in sorted(core_src.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        rel = path.relative_to(core_src).as_posix()
        for text in _texts(tree):
            normalized_text = _normalize(text)
            for token in TOKENS:
                hits = _count_token(token, text, normalized_text)
                if hits:
                    counts[(rel, token)] += hits
    return counts


def read_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    entries = {}
    if not path.exists():
        return entries
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rel, token, number, *reason = line.split("\t")
        entries[(rel, token)] = (int(number), reason[0] if reason else "")
    return entries


def _existing_header(path: Path) -> str:
    """The baseline's leading blank/comment lines, kept verbatim by --write-baseline."""
    if not path.exists():
        return _DEFAULT_HEADER
    header_lines = []
    for line in path.read_text().splitlines(keepends=True):
        if line.strip() == "" or line.lstrip().startswith("#"):
            header_lines.append(line)
        else:
            break
    return "".join(header_lines) if header_lines else _DEFAULT_HEADER


def write_baseline(path: Path, counts: Counter) -> None:
    """Record the current counts.

    A pair with an unchanged count keeps its reason; a new or changed pair gets
    TODO_REASON, which the check refuses until a maintainer writes one.
    """
    existing = read_baseline(path)
    header = _existing_header(path)
    lines = []
    for key, n in sorted(counts.items()):
        recorded = existing.get(key)
        if recorded is not None and recorded[0] == n and recorded[1]:
            reason = recorded[1]
        else:
            reason = TODO_REASON
        lines.append(f"{key[0]}\t{key[1]}\t{n}\t{reason}")
    body = "\n".join(lines)
    path.write_text(header + body + ("\n" if body else ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-src", type=Path, default=CORE_SRC)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true",
                        help="record today's counts; a new or changed (file, token) pair"
                             " is written with TODO-reason, which must then be replaced by hand")
    args = parser.parse_args()
    counts = count(args.core_src)
    if args.write_baseline:
        write_baseline(args.baseline, counts)
        return 0
    baseline = read_baseline(args.baseline)
    problems = []
    for key, (n, reason) in sorted(baseline.items()):
        if reason in ("", TODO_REASON):
            problems.append(
                f"TODO   {key[0]}: {key[1]} x{n} -- baseline line has no hand-written reason"
            )
    for key, n in sorted(counts.items()):
        recorded = baseline.get(key)
        if recorded is None:
            problems.append(f"NEW    {key[0]}: {key[1]} x{n} -- core must not name OpenFOAM layout")
        elif n > recorded[0]:
            problems.append(f"GREW   {key[0]}: {key[1]} {recorded[0]} -> {n}")
        elif n < recorded[0]:
            problems.append(f"shrank {key[0]}: {key[1]} {recorded[0]} -> {n}; edit the baseline to {n}")
    for key, (n, _reason) in sorted(baseline.items()):
        if key not in counts:
            problems.append(f"shrank {key[0]}: {key[1]} {n} -> 0; delete this baseline line")
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
