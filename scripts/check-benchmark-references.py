#!/usr/bin/env python3
"""Every benchmark reference under benchmarks/ is a valid point reference.

A reference is supplied data: an agent passes its path in a comparison
request. This gate keeps the committed ones loadable, their citations
resolvable and their units in core's table
(omnidriver.core.quantities.load_point_reference). It checks form, not
truth. Whether a value is the source's own is a review question, answered
in each file's `sources` and in the review table of the task that wrote it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omnidriver.core.quantities import PointReferenceError, load_point_reference

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
