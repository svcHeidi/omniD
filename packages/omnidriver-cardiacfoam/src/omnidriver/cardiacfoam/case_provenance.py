"""Solver-declared case classification for the provenance snapshot.

``generated_output_globs`` excludes ``constant/C``, ``Cx``, ``Cy``, ``Cz`` and
``skewness``: mesh-diagnostic byproducts an exhaustive grep across ``src/``
and ``applications/`` found no reads of anywhere in the solver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Fixed names, independent of the resolved model -- unlike the 0/ solver
# fields, these mesh-diagnostic byproducts are never renamed by a dictionary
# key.
_GENERATED_OUTPUT_GLOBS: tuple[str, ...] = (
    "constant/C",
    "constant/Cx",
    "constant/Cy",
    "constant/Cz",
    "constant/skewness",
)


def generated_output_globs(
    case_root: Path,
    resolved_case: dict[str, Any],
) -> tuple[str, ...]:
    """``constant/C``, ``Cx``, ``Cy``, ``Cz``, ``skewness`` -- read by nothing."""
    del case_root, resolved_case
    return _GENERATED_OUTPUT_GLOBS
