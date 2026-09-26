"""Where the cardiacFoam monorepo is, when this checkout sits inside one.

Moved from core's ``core.specs.paths`` 2026-09-26 (spec
2026-09-26-core-generality-design.md §2, A6). Its only users are cardiac
scripts and tests; shipped core names no solver. Body unchanged.
"""
from __future__ import annotations

from pathlib import Path


def cardiacfoam_monorepo_root(start: Path | None = None) -> Path | None:
    """Walk parent directories looking for the full cardiacFoam monorepo root.

    Returns the first ancestor of ``start`` (default: this file) that has
    both ``tutorials/`` and ``applications/`` siblings, or ``None`` in a
    standalone checkout (the normal case)."""
    current = (start or Path(__file__)).resolve()
    for parent in current.parents:
        if (parent / "tutorials").exists() and (parent / "applications").exists():
            return parent
    return None
