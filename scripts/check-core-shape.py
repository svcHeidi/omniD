#!/usr/bin/env python3
"""Core must not assume the world is an OpenFOAM case (spec 2026-09-25 §6).

Counts OpenFOAM layout tokens in core's identifiers and string literals
(comments and docstrings are prose, not coupling) per (file, token), and
compares them with scripts/core-shape-baseline.txt. The baseline is recorded
debt, not a waiver list:
- a new (file, token) pair fails;
- a higher count fails;
- a count that shrank also fails until the baseline is edited to match, so
  the debt can only go down.
Baseline line format: ``<path relative to core src>\\t<token>\\t<count>\\t<reason>``.
"""
from __future__ import annotations

import argparse
import ast
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
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
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
            for token in TOKENS:
                hits = text.count(token)
                if hits:
                    counts[(rel, token)] += hits
    return counts


def read_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    entries = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rel, token, number, *reason = line.split("\t")
        entries[(rel, token)] = (int(number), reason[0] if reason else "")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-src", type=Path, default=CORE_SRC)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true",
                        help="record today's counts; every reason must then be written by hand")
    args = parser.parse_args()
    counts = count(args.core_src)
    if args.write_baseline:
        lines = [f"{rel}\t{token}\t{n}\tTODO-reason" for (rel, token), n in sorted(counts.items())]
        args.baseline.write_text("\n".join(lines) + "\n")
        return 0
    baseline = read_baseline(args.baseline)
    problems = []
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
