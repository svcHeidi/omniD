"""cardiacSubstrateFOAM's workflow steps: ``step()`` mirrors native ``Allrun``'s ``<utility> -case .``."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.tutorial_records import WorkflowStep
from omnidriver.core.utility_catalog import load_utility_manifests

#: Every utility reads this convention dictionary, though native ``Allrun``
#: never declares it as a dependency.
CONV = "system/coordinatesConventionDict"


def step(step_id: str, utility: str, *, consumes: tuple[str, ...]) -> WorkflowStep:
    """The step running ``utility``, producing what its manifest says it always writes; an output the manifest marks
    optional is written only under some settings, so a step does not require it."""
    manifest = load_utility_manifests(Path(__file__).parents[1] / "utilities")[utility]
    return WorkflowStep(
        step_id=step_id,
        command=(utility, "-case", "."),
        consumes=(f"system/{utility}Dict", *consumes),
        produces=tuple(produced.path_pattern for produced in manifest.produces if not produced.optional),
    )
