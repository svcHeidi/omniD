"""The solver command cardiacFOAM authorizes; its utilities are authorized by their manifests."""

from __future__ import annotations

# Only solver_commands() feeds the artifact-producer heuristic in
# normalize_workflow_dag; every other command this plugin runs comes through
# its utility manifests or core's own authorization.
CARDIAC_SOLVER_COMMANDS = frozenset({"cardiacFoam"})


def solver_commands() -> frozenset[str]:
    """This plugin's artifact-producing solver commands."""
    return CARDIAC_SOLVER_COMMANDS
