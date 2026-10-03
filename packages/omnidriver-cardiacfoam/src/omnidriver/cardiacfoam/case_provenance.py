"""Solver-declared case classification for the provenance snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Mesh-diagnostic byproducts that nothing in the solver's src/ or applications/
# reads. Fixed names, independent of the resolved model -- unlike the 0/ solver
# fields, no dictionary key renames them.
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
