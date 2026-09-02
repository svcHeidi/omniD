from __future__ import annotations

from dataclasses import dataclass

from omnidriver.core.planning_types import StrictDiagnostic


@dataclass(frozen=True)
class LaunchReadiness:
    """One consolidated verdict over a plan's pre-execution readiness.

    ``structural_ok`` and ``environment_ok`` are exposed individually, not
    just folded into ``launchable``, because some CLI call sites only ever
    need one half: ``action=plan`` reports readiness without requiring the
    execution environment to be available (planning must work on a machine
    without OpenFOAM installed), while the environment gate only applies
    once a run is actually about to be dispatched -- and by that point
    structural validity has already been established separately. Route both
    kinds of call sites through this same predicate; just read the field
    each site actually needs.
    """

    launchable: bool
    structural_ok: bool
    environment_ok: bool
    has_warnings: bool
    blocking_reason: str | None


def is_launchable(
    *,
    plan_status: str,
    environment_diagnostics: tuple[StrictDiagnostic, ...] = (),
) -> LaunchReadiness:
    """Compute launch readiness from a plan's status and environment diagnostics.

    ``plan_status`` is ``StrictPlanReport.status`` ("ok"/"failed"), already
    computed upstream from structural/semantic ``plan_diagnostics`` only --
    warn-only diagnostic sets (function-object field warnings, environment
    diagnostics) never factor into it by design, so a sampled-field or
    environment warning can never fail a plan.

    ``environment_diagnostics`` is the plan's execution-readiness diagnostics
    (e.g. missing OpenFOAM/MPI/solver binary). Only ``level == "error"``
    entries block launch; ``level == "warning"`` entries are surfaced via
    ``has_warnings`` but never block.
    """
    structural_ok = plan_status == "ok"
    environment_errors = tuple(
        diagnostic for diagnostic in environment_diagnostics if diagnostic.level == "error"
    )
    environment_warnings = tuple(
        diagnostic for diagnostic in environment_diagnostics if diagnostic.level == "warning"
    )
    environment_ok = not environment_errors
    has_warnings = bool(environment_warnings)
    launchable = structural_ok and environment_ok

    blocking_reason: str | None = None
    if not structural_ok:
        blocking_reason = "plan is not structurally/semantically valid"
    elif not environment_ok:
        blocking_reason = "execution environment is not ready"

    return LaunchReadiness(
        launchable=launchable,
        structural_ok=structural_ok,
        environment_ok=environment_ok,
        has_warnings=has_warnings,
        blocking_reason=blocking_reason,
    )


def is_execution_successful(workflow_status: str) -> bool:
    """Whether a workflow status is the strict success terminal state.

    Mirrors the strict success contract shared by step and run: only
    ``"completed"`` counts. Any other status (``pending``, ``running``,
    ``failed``, ``skipped``) is not a success at this boundary -- decisions
    derive from status, never from a raw subprocess exit code.
    """
    return workflow_status == "completed"
