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

Matching is normalised (casefold, with ``_``/``.``/``-`` stripped from both
the token and the scanned text) so a snake_case or otherwise-punctuated
spelling of the same layout concept is counted, not just the token's literal
form (review 2026-09-25, C-I1: ``touch_case_foam`` is the same coupling as
``case.foam``). Two tokens carry a hand-tuned exception to that normalisation
rather than a per-file special case:
- ``FOAM_`` stays an exact, case-sensitive substring match with no boundary,
  because a boundary would stop it catching ``OPENFOAM_*`` -- itself real
  coupling (review: "Should FOAM_ require a boundary? No.").
- ``processor`` gets a left boundary (not preceded by a letter) on the
  normalised text, so ``processor_dir`` still counts but ``postprocessor``/
  ``preprocessor`` do not (review: "Does processor have the same problem?").

``--write-baseline`` preserves the file's header and every hand-written
reason for a (file, token) pair whose count did not change; a new pair or a
changed count is written with the placeholder reason ``TODO-reason``, which
a maintainer must replace by hand. The normal check fails, naming the line,
while any ``TODO-reason`` remains (C-I2): a guard whose own maintenance flag
can silently erase or bless debt is weaker than the invariant it claims to
enforce.
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
    # Added 2026-09-26 (R2 fix, finding M7): A2 removed core's own "start
    # time"/"time-indexed" vocabulary (CaseIntrospectionCapability
    # .selected_start_time, DataArtifact.time_indexed, the {time} path
    # placeholder), but nothing in this list guarded against it regrowing --
    # only the specific assertions in test_instance_directories.py
    # ::test_the_time_vocabulary_is_gone covered {time}/time_indexed, and
    # nothing covered "start time" itself.
    "start_time", "startTime", "latestTime", "time_indexed", "{time}",
)

# Chars treated as equivalent-to-absent when comparing spellings: they
# separate words in an identifier the way camelCase capitalisation or a
# literal "." does in the token's own spelling.
_SEPARATORS = str.maketrans("", "", "_.-")

# processor's left boundary: not preceded by a letter, so postprocessor/
# preprocessor are excluded but processor_dir (boundary at the underscore,
# stripped before this regex runs) is not.
_PROCESSOR_RE = re.compile(r"(?<![a-z])processor")

TODO_REASON = "TODO-reason"

_DEFAULT_HEADER = (
    "# Recorded OpenFOAM-layout debt in core (spec 2026-09-25 §6). Format:\n"
    "# <path relative to core src>\\t<token>\\t<count>\\t<reason>\n"
    "# This is debt, not a waiver: scripts/check-core-shape.py fails on any new\n"
    "# (file, token) pair, any higher count, and any count that shrank without\n"
    "# this file being edited to match -- so the total can only go down.\n"
)


def _normalize(text: str) -> str:
    return text.translate(_SEPARATORS).casefold()


def _count_token(token: str, raw_text: str, normalized_text: str) -> int:
    if token == "FOAM_":
        # Deliberately unnormalised: see the module docstring.
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
    """String literals this module's own docstring calls prose, not
    coupling: not only body[0] (a module/class/function's true docstring),
    but also a bare string statement anywhere else in a body -- the
    attribute/field "docstring" convention this codebase's own house style
    uses for a dated correction (CLAUDE.md: "record the correction with a
    date rather than silently overwriting it").

    Corrected 2026-09-26 (R2 fix, finding M7): before this, only body[0]
    counted, so a dated correction on a dataclass field (e.g.
    ``DataArtifact.instance_indexed``'s "Renamed from time_indexed ...")
    was scanned as a literal despite being exactly the prose the module
    docstring already says is exempt -- discovered when M7 added
    ``time_indexed`` to TOKENS and two already-committed, pre-existing dated
    corrections became new "hits" with no code change at all.
    """
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
    """The leading run of blank/comment lines in an existing baseline file,
    preserved verbatim by --write-baseline; a fresh file gets the default."""
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
    """Record today's counts. A (file, token) pair whose count is unchanged
    from the existing baseline keeps its hand-written reason; a new pair or
    one whose count changed (grew or shrank) gets TODO_REASON, which the
    normal check then refuses until a maintainer replaces it by hand."""
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
