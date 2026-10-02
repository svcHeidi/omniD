#!/usr/bin/env python3
"""Render the plugin capability seam table into ARCHITECTURE.md; ``--check`` verifies the committed table against a fresh render."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omnidriver.core.capability_seams import (
    architecture_path,
    collect_seams,
    render,
    splice,
    validate_tiers,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if ARCHITECTURE.md is not up to date, writing nothing",
    )
    args = parser.parse_args()

    architecture = architecture_path()
    seams = collect_seams()

    problems = validate_tiers(seams)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(1)

    document = architecture.read_text()
    updated = splice(document, render(seams))

    if args.check:
        if document != updated:
            print(
                "ARCHITECTURE.md capability seam table is stale. "
                "Regenerate with: python3 scripts/export-capability-seams.py",
                file=sys.stderr,
            )
            return 1
        print("ARCHITECTURE.md capability seam table is up to date.")
        return 0

    architecture.write_text(updated)
    print(f"Wrote {len(seams)} capability seams to {architecture.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
