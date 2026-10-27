#!/usr/bin/env python3
"""Every benchmark reference under benchmarks/ is a valid point reference.

The gate checks form (loadable, citations resolvable, units in core's table), not truth.
A benchmarks/<name>/requests folder is checked too: each request's `reference` resolves
and `SHA256SUMS` lists exactly its requests with their digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from omnidriver.core.quantities import PointReferenceError, load_point_reference

REPO_ROOT = Path(__file__).resolve().parents[1]


def request_failures(requests: Path) -> list[str]:
    failures = []
    files = sorted(requests.glob("*.json"))
    sums = requests / "SHA256SUMS"
    listed = {}
    if sums.is_file():
        for line in sums.read_text().splitlines():
            digest, _, name = line.partition("  ")
            listed[name] = digest
    for path in files:
        reference = (requests / json.loads(path.read_text())["reference"]).resolve()
        if not reference.is_file():
            failures.append(f"{path}: reference {reference} does not exist")
        if listed.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            failures.append(f"{path}: not the digest in SHA256SUMS")
    for name in sorted(set(listed) - {path.name for path in files}):
        failures.append(f"{sums}: lists {name}, which is not a request")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=REPO_ROOT / "benchmarks")
    args = parser.parse_args(argv)
    files = sorted(args.dir.glob("*.json"))
    if not files:
        print(f"FAIL no references under {args.dir}; this gate would check nothing", file=sys.stderr)
        return 1
    failures = []
    for path in files:
        try:
            reference = load_point_reference(path)
        except PointReferenceError as exc:
            failures.append(str(exc))
            continue
        if reference.reference_id != path.stem:
            failures.append(f"{path.name}: id {reference.reference_id!r} is not the file name")
            continue
        resolved = sorted(label for label, point in reference.points.items() if point.coordinates is not None)
        print(f"ok {path.name}: {len(reference.points)} points, coordinates for {resolved}")
    for requests in sorted(args.dir.glob("*/requests")):
        problems = request_failures(requests)
        failures.extend(problems)
        if not problems:
            print(f"ok {requests.relative_to(args.dir)}: {len(list(requests.glob('*.json')))} requests match SHA256SUMS")
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
