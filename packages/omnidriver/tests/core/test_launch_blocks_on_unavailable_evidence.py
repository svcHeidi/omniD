"""A required check that cannot run prevents the claim that depends on it.

See docs/superpowers/specs/2026-09-18-coverage-as-evidence.md §5.

`is_launchable` decides from `plan_status` and environment *diagnostics* only.
A stage that never ran emits no diagnostics, so `environment_ok = not ()` is
True and the gate opens. That is the launch-side half of the same defect the
scoring had: absence of evidence read as evidence of absence of problems.

The distinction the gate must make:

  unavailable    the check was owed and could not run -- blocks
  not_requested  an operator declined it -- does not block, but is recorded
  not_applicable there was nothing to check -- does not block

These test `is_launchable` directly with constructed audit items rather than
through a plugin, because the rule is core's and must hold for any adapter,
including ones that do not exist yet.
"""
from __future__ import annotations

from omnidriver.core.planning_types import SimulationAuditItem
from omnidriver.core.runtime.launch_readiness import is_launchable


def _item(stage: str, status: str, max_points: int = 10) -> SimulationAuditItem:
    return SimulationAuditItem(
        stage=stage,
        status=status,
        points=0,
        max_points=max_points,
        summary=f"{stage} is {status}",
    )


def test_an_unavailable_check_blocks_launch() -> None:
    """The tool a check needs was absent, so nothing is known about that stage."""
    readiness = is_launchable(
        plan_status="ok",
        environment_diagnostics=(),
        simulation_audit=(_item("mesh_geometry", "unavailable"),),
    )

    assert readiness.launchable is False
    assert readiness.blocking_reason is not None
    assert "mesh_geometry" in readiness.blocking_reason


def test_a_declined_check_does_not_block_launch() -> None:
    """An operator may still choose to run with a check switched off."""
    readiness = is_launchable(
        plan_status="ok",
        environment_diagnostics=(),
        simulation_audit=(_item("environment_preflight", "not_requested"),),
    )

    assert readiness.launchable is True


def test_an_inapplicable_check_does_not_block_launch() -> None:
    """Nothing to check is not a missing check."""
    readiness = is_launchable(
        plan_status="ok",
        environment_diagnostics=(),
        simulation_audit=(_item("dictionary_resolution", "not_applicable"),),
    )

    assert readiness.launchable is True


def test_a_plan_with_no_audit_still_launches() -> None:
    """Callers that predate coverage must keep working unchanged.

    `is_launchable` is called from several CLI paths; a missing audit means
    "no coverage information supplied", which must not be read as a gap.
    """
    readiness = is_launchable(plan_status="ok", environment_diagnostics=())

    assert readiness.launchable is True
