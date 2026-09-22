from __future__ import annotations

from dataclasses import dataclass

from omnidriver.core.planning_types import SimulationAuditItem, StrictDiagnostic


@dataclass(frozen=True)
class LaunchReadiness:
    """One consolidated verdict over a plan's pre-execution readiness.

    ``structural_ok`` and ``environment_ok`` are exposed individually, not
    just folded into ``launchable``, because some CLI call sites only ever
    need one half: ``action=plan`` reports readiness without requiring the
    execution environment to be available (planning must work without the
    selected runtime installed), while the environment gate only applies
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
    #: False when a required check could not run. Exposed alongside the other
    #: two halves for the same reason: a call site reporting readiness needs to
    #: distinguish "we looked and it is wrong" from "we could not look".
    coverage_ok: bool = True


#: A stage whose check was owed and could not run. The plan says nothing about
#: it, so nothing may be claimed on its behalf. `not_requested` (an operator
#: declined it) and `not_applicable` (there was nothing to check) are recorded
#: but do not block -- see the spec's §5 table.
_BLOCKING_OUTCOME = "unavailable"


def is_launchable(
    *,
    plan_status: str,
    environment_diagnostics: tuple[StrictDiagnostic, ...] = (),
    simulation_audit: tuple[SimulationAuditItem, ...] = (),
) -> LaunchReadiness:
    """Compute launch readiness from a plan's status and environment diagnostics.

    ``plan_status`` is ``StrictPlanReport.status`` ("ok"/"failed"), already
    computed upstream from structural/semantic ``plan_diagnostics`` only --
    warn-only diagnostic sets (function-object field warnings, environment
    diagnostics) never factor into it by design, so a sampled-field or
    environment warning can never fail a plan.

    ``environment_diagnostics`` is the plan's execution-readiness diagnostics
    (for example, missing runtime, launcher, or solver executable). Only
    ``level == "error"``
    entries block launch; ``level == "warning"`` entries are surfaced via
    ``has_warnings`` but never block.

    ``simulation_audit`` supplies coverage. A stage whose check was owed and
    could not run (``unavailable``) blocks: the plan says nothing about it, so
    nothing may be claimed on its behalf. ``not_requested`` and
    ``not_applicable`` are recorded and do not block. Omitting the argument
    means "no coverage information supplied" and never blocks, so the planning
    call sites that only read ``structural_ok`` are unaffected -- offline
    planning must keep working with the runtime absent.

    **Wired to dispatch 2026-09-22** (audit finding C2). The dispatch-time gate
    passes ``simulation_audit``; planning call sites still omit it and read
    ``structural_ok`` only, so offline planning keeps working with the runtime
    absent. Read ``coverage_ok`` as "no required check reported ``unavailable``
    to this call" -- for a call that was given no audit, that remains a
    statement about the call, not a guarantee about the run.

    Concretely: ``cli._refuse_environment_errors`` (the one dispatch-time gate)
    now passes ``context.simulation_audit``, which ``StepExecutionContext``
    carries. An entry-based plan populates it from
    ``StrictPlanReport.simulation_audit``, so a stage genuinely scored
    ``unavailable`` there blocks launch. A RunDocument-based execution still
    supplies an empty audit -- ``schemas/run-document.json`` has no field for
    one yet -- so that path's ``coverage_ok`` is "no coverage information was
    available to check", same as omitting the argument entirely; it is not
    evidence that nothing is missing. Nothing in this codebase emits
    ``unavailable`` yet either (no ``_score_from_diagnostics`` call site passes
    that outcome as of this date), so this gate is correct and currently
    unfed for both paths -- the fix that makes it fire is a real check
    starting to report the outcome it was always able to model.
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

    Mirrors the strict success contract shared by step and run: only
    ``"completed"`` counts. Any other status (``pending``, ``running``,
    ``failed``, ``skipped``) is not a success at this boundary -- decisions
    derive from status, never from a raw subprocess exit code.
    """
    return workflow_status == "completed"
