"""Solver-declared case classification for the provenance snapshot.

``required_inputs`` returns ``()`` until full model-dependent input
enumeration lands (which ``0/`` fields exist depends on the configured solver
and ionic model, and their locations resolve by a backward
``Time::findInstance`` search). Safe meanwhile: an unclassified file falls
back to ``required_input``, so nothing here can under-classify one.

``generated_output_globs`` excludes ``constant/C``, ``Cx``, ``Cy``, ``Cz`` and
``skewness``: mesh-diagnostic byproducts an exhaustive grep across ``src/``
and ``applications/`` found no reads of anywhere in the solver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.plugin_capabilities import ResolvedInput

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


def required_inputs(
    case_root: Path,
    resolved_case: dict[str, Any],
) -> tuple[ResolvedInput, ...]:
    """Deferred: returns ``()`` until input enumeration lands. See the module
    docstring for why ``()`` is safe."""
    del case_root, resolved_case
    return ()


def generated_output_globs(
    case_root: Path,
    resolved_case: dict[str, Any],
) -> tuple[str, ...]:
    """``constant/C``, ``Cx``, ``Cy``, ``Cz``, ``skewness`` -- read by nothing."""
    del case_root, resolved_case
    return _GENERATED_OUTPUT_GLOBS
