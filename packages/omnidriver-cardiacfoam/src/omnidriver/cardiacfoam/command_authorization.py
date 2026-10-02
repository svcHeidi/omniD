"""The workflow commands cardiacFoam authorizes: its solver binary, its utilities and the utility manifests under its utilities root."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

# Split in two because core consumes them differently: only
# solver_commands() feeds the artifact-producer heuristic in
# normalize_workflow_dag, so conflating them would credit a post-processing
# utility with the solver's outputs. Their union is the plugin's
# accept-surface contribution; neither is core knowledge.
CARDIAC_SOLVER_COMMANDS = frozenset({"cardiacFoam"})

# gradientReconstructionOrder (applications/test/gradientReconstructionOrder)
# is listed here rather than coming through utility_manifests() because it
# ships no utility.manifest.toml, though it is a live workflow step in
# manufactured_eikonal_ecg.py's gradient_reconstruction=True path.
#
# The error_localisation_analysis=True path's other two steps need no entry:
# `postProcess` is core-authorized generically (CORE_NEUTRAL_COMMANDS), and
# the analysis script is invoked by its own relative path, which
# workflow_runner._resolve_command treats as an explicit opt-in regardless of
# authorization, the same as any case's own Allrun/Allclean script.
CARDIAC_AUXILIARY_COMMANDS = frozenset({
    "gradientReconstructionOrder",
})


def solver_commands() -> frozenset[str]:
    """This plugin's artifact-producing solver commands."""
    return CARDIAC_SOLVER_COMMANDS


def auxiliary_commands() -> frozenset[str]:
    """Authorized plugin commands that do not produce the run's artifacts."""
    return CARDIAC_AUXILIARY_COMMANDS


#: This plugin's own bundled ``utility.manifest.toml`` sidecars -- package
#: data shipped inside ``omnidriver-cardiacfoam`` (see that package's
#: pyproject.toml ``[tool.setuptools.package-data]``), not read from a
#: sibling cardiacFoam monorepo checkout. core has no knowledge of this path;
#: it only ever sees the roots this function hands it.
_BUNDLED_UTILITIES_ROOT = Path(__file__).parent / "utilities"


def utility_roots() -> tuple[Path, ...]:
    """Roots holding this plugin's ``utility.manifest.toml`` sidecars."""
    return (_BUNDLED_UTILITIES_ROOT,) if _BUNDLED_UTILITIES_ROOT.is_dir() else ()


@lru_cache(maxsize=1)
def utility_manifests() -> Mapping[str, Any]:
    """Parse this plugin's utility manifests. Cached: parsing walks the tree.

    Returns a read-only view: the cache hands the same object to every caller,
    so a mutable dict would let one consumer corrupt the authorization input of
    all the others.
    """
    from omnidriver.core.utility_catalog import load_utility_manifests

    manifests: dict[str, Any] = {}
    for root in utility_roots():
        manifests.update(load_utility_manifests(root))
    return MappingProxyType(manifests)
