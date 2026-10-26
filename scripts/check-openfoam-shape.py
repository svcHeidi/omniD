#!/usr/bin/env python3
"""Fail when the OpenFOAM layer names cardiac vocabulary beyond the recorded baseline, scripts/openfoam-shape-baseline.txt.

The layer serves every OpenFOAM-based solver, so its source, data and prose name none of them. Tokens are counted per
(file, token) over the whole text of every file under the package's src; a new, higher or shrunk count fails, so the
baseline can only go down.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENFOAM_SRC = REPO_ROOT / "packages/omnidriver-openfoam/src/omnidriver/openfoam"
BASELINE = REPO_ROOT / "scripts/openfoam-shape-baseline.txt"
#: token -> pattern. Words are matched case-insensitively; ``Vm`` is matched as itself, since ``vm`` alone is no word.
TOKENS = {
    "cardiac": re.compile(r"cardiac", re.IGNORECASE),
    "electro": re.compile(r"electro(?!de)", re.IGNORECASE),
    "myocard": re.compile(r"myocard", re.IGNORECASE),
    "purkinje": re.compile(r"purkinje", re.IGNORECASE),
    "heart": re.compile(r"heart", re.IGNORECASE),
    "ionic": re.compile(r"ionic", re.IGNORECASE),
    "singleCell": re.compile(r"single_?cell", re.IGNORECASE),
    "Vm": re.compile(r"(?<![A-Za-z])Vm(?![a-z])"),
    "Iion": re.compile(r"(?<![A-Za-z])Iion(?![a-z])"),
}
_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".md", ".txt")


def count(src: Path) -> Counter:
    counts: Counter = Counter()
    for path in sorted(item for item in src.rglob("*") if item.is_file() and item.suffix in _SUFFIXES):
        text = path.read_text(errors="replace")
        for token, pattern in TOKENS.items():
            hits = len(pattern.findall(text))
            if hits:
                counts[(path.relative_to(src).as_posix(), token)] = hits
    return counts


def read_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    entries = {}
    for line in path.read_text().splitlines() if path.exists() else ():
        if line.strip() and not line.startswith("#"):
            rel, token, number, *reason = line.split("\t")
            entries[(rel, token)] = (int(number), reason[0] if reason else "")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=OPENFOAM_SRC)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()
    counts = count(args.src)
    baseline = read_baseline(args.baseline)
    problems = [
        f"TODO   {rel}: {token} x{n} -- baseline line has no hand-written reason"
        for (rel, token), (n, reason) in sorted(baseline.items()) if not reason
    ]
    for key, n in sorted(counts.items()):
        recorded = baseline.get(key)
        if recorded is None:
            problems.append(f"NEW    {key[0]}: {key[1]} x{n} -- the OpenFOAM layer must not name a solver's vocabulary")
        elif n > recorded[0]:
            problems.append(f"GREW   {key[0]}: {key[1]} {recorded[0]} -> {n}")
        elif n < recorded[0]:
            problems.append(f"shrank {key[0]}: {key[1]} {recorded[0]} -> {n}; edit the baseline to {n}")
    problems += [
        f"shrank {rel}: {token} {n} -> 0; delete this baseline line"
        for (rel, token), (n, _reason) in sorted(baseline.items()) if (rel, token) not in counts
    ]
    for problem in problems:
        print(problem)
    if not problems:
        print("OpenFOAM layer shape OK: no cardiac vocabulary beyond the recorded baseline.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
