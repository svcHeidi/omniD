"""Solver-declared case classification for the provenance snapshot."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from omnidriver.core.plugin_interface import CaseRuntimeConventions
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions

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


def case_runtime_conventions() -> CaseRuntimeConventions:
    """OpenFOAM's generated paths and ``local/``.

    A tutorial's ``Allrun`` writes its options into ``local/``, which the case's dictionaries ``#includeIfPresent``; one
    left by a native run would override what omniD writes, so staging drops it."""
    conventions = openfoam_case_runtime_conventions()
    return replace(conventions, generated_directory_names=(*conventions.generated_directory_names, "local"))
