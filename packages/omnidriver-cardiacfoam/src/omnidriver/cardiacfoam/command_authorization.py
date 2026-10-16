"""The workflow commands cardiacFoam authorizes: its solver binary, its utilities and the utility manifests under its utilities root."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

# Only solver_commands() feeds the artifact-producer heuristic in
# normalize_workflow_dag; every other command this plugin runs comes through
# utility_manifests() or core's own authorization.
CARDIAC_SOLVER_COMMANDS = frozenset({"cardiacFoam"})


def solver_commands() -> frozenset[str]:
    """This plugin's artifact-producing solver commands."""
    return CARDIAC_SOLVER_COMMANDS


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
