from __future__ import annotations

from dataclasses import dataclass

from omnidriver.core.planning_types import SimulationAuditItem, StrictDiagnostic


@dataclass(frozen=True)
class LaunchReadiness:
    """One consolidated verdict over a plan's pre-execution readiness.

    ``structural_ok`` and ``environment_ok`` are exposed individually because
    some call sites need only one -- planning must work without the runtime
    installed, while the environment gate only applies once a run is about
    to be dispatched.
    """

    launchable: bool
    structural_ok: bool
    environment_ok: bool
    has_warnings: bool
    blocking_reason: str | None
    #: False when a required check could not run, distinct from one that ran and failed.
    coverage_ok: bool = True


# Owed check that couldn't run.
_BLOCKING_OUTCOME = "unavailable"


def is_launchable(
    *,
    plan_status: str,
    environment_diagnostics: tuple[StrictDiagnostic, ...] = (),
    simulation_audit: tuple[SimulationAuditItem, ...] = (),
) -> LaunchReadiness:
    """Compute launch readiness from a plan's status and environment diagnostics.

    ``plan_status`` is ``StrictPlanReport.status`` ("ok", "blocked" when the
    plan is valid but its environment preflight holds an error, or "failed"); warn-only
    diagnostics never factor into it. Only ``environment_diagnostics`` entries
    with ``level == "error"`` block launch; ``level == "warning"`` entries only
    set ``has_warnings``. In ``simulation_audit``, a stage scored
    ``unavailable`` blocks launch (a required check could not run). Omitting
    ``simulation_audit`` means no coverage information was supplied, and never
    blocks -- offline planning must keep working with the runtime absent.
    """
    structural_ok = plan_status in {"ok", "blocked"}
    environment_errors = tuple(
        diagnostic for diagnostic in environment_diagnostics if diagnostic.level == "error"
    )
    environment_warnings = tuple(
        diagnostic for diagnostic in environment_diagnostics if diagnostic.level == "warning"
    )
    environment_ok = not environment_errors
    has_warnings = bool(environment_warnings)
    unavailable = tuple(
        item.stage for item in simulation_audit
        if item.status == _BLOCKING_OUTCOME
    )
    coverage_ok = not unavailable
    launchable = structural_ok and environment_ok and coverage_ok

    blocking_reason: str | None = None
    if not structural_ok:
        blocking_reason = "plan is not structurally/semantically valid"
    elif not environment_ok:
        blocking_reason = "execution environment is not ready"
    elif not coverage_ok:
        blocking_reason = (
            "required checks could not run, so this plan is unverified: "
            + ", ".join(unavailable)
        )

    return LaunchReadiness(
        launchable=launchable,
        structural_ok=structural_ok,
        environment_ok=environment_ok,
        has_warnings=has_warnings,
        blocking_reason=blocking_reason,
        coverage_ok=coverage_ok,
    )


def is_execution_successful(workflow_status: str) -> bool:
    """Whether a workflow status is the strict success terminal state.

    Only ``"completed"`` counts; decisions derive from status, never a raw
    subprocess exit code.
    """
    return workflow_status == "completed"
