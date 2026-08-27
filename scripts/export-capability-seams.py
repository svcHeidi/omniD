#!/usr/bin/env python3
#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Script
#     export-capability-seams
#
# Description
#     Renders the plugin capability seam table into ARCHITECTURE.md.
#
#     Thin CLI over openfoam_driver.core.capability_seams, which owns the
#     parsing and rendering: the conformance tests import that module
#     directly, so there is exactly one parser.
#
#     Run with --check to verify the committed ARCHITECTURE.md table matches a
#     fresh render; the conformance test uses that mode.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omnidriver.core.capability_seams import (
    architecture_path,
    collect_seams,
    render,
    splice,
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
