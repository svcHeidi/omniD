from __future__ import annotations

from typing import Any

from omnidriver.core.planning_types import (
    StrictDiagnostic,
    SimulationAuditItem,
    has_error,
    has_warning,
)
from .models import DataArtifact


#: The stages every solver has. A check that depends on a solver's file formats
#: is a plugin diagnostic (``get_plan_diagnostics``), not a stage.
_READINESS_WEIGHTS = {
    "workflow_preparation": 20,
    "artifact_prediction": 15,
    "environment_preflight": 10,
}


def _score_from_diagnostics(
    *,
    stage: str,
    diagnostics: tuple[StrictDiagnostic, ...],
    success_summary: str,
    warning_summary: str,
    error_summary: str,
    evidence: dict[str, Any] | None = None,
) -> SimulationAuditItem:
    """Score one stage from the diagnostics its check produced."""
    max_points = _READINESS_WEIGHTS[stage]
    if has_error(diagnostics):
        return SimulationAuditItem(
            stage=stage,
            status="blocked",
            points=0,
            max_points=max_points,
            summary=error_summary,
            evidence=evidence or {},
        )
    if has_warning(diagnostics):
        return SimulationAuditItem(
            stage=stage,
            status="warning",
            points=max_points // 2,
            max_points=max_points,
            summary=warning_summary,
            evidence=evidence or {},
        )
    return SimulationAuditItem(
        stage=stage,
        status="passed",
        points=max_points,
        max_points=max_points,
        summary=success_summary,
        evidence=evidence or {},
    )


def _build_simulation_audit(
    *,
    workflow_dag: dict[str, Any] | None,
    artifacts: tuple[DataArtifact, ...],
    workflow_diagnostics: tuple[StrictDiagnostic, ...],
    command_diagnostics: tuple[StrictDiagnostic, ...],
    environment_diagnostics: tuple[StrictDiagnostic, ...],
) -> tuple[tuple[SimulationAuditItem, ...], dict[str, Any]]:
    items = [
        _score_from_diagnostics(
            stage="workflow_preparation",
            diagnostics=workflow_diagnostics,
            success_summary="The workflow DAG is normalized into executable argv-style steps.",
            warning_summary="The workflow DAG is executable, but normalization emitted warnings.",
            error_summary="The workflow DAG is missing or invalid, so strict execution cannot start.",
            evidence={
                "step_count": 0 if workflow_dag is None else len(workflow_dag.get("steps", ())),
                "step_ids": [] if workflow_dag is None else [
                    str(step.get("id", "")) for step in workflow_dag.get("steps", ())
                ],
            },
        ),
        _score_from_diagnostics(
            stage="artifact_prediction",
            diagnostics=command_diagnostics,
            success_summary="The planner predicts raw data artifacts and links them to workflow steps.",
            warning_summary="Artifacts are predicted, but coverage warnings remain.",
            error_summary="The planner cannot reliably predict this run's data artifacts.",
            evidence={
                "artifact_count": len(artifacts),
                "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            },
        ),
        _score_from_diagnostics(
            stage="environment_preflight",
            diagnostics=environment_diagnostics,
            success_summary="The current environment satisfies the commands declared by the workflow.",
            warning_summary="The environment can be used, but preflight emitted warnings.",
            error_summary="The current environment is missing executables or runtime setup needed to run.",
            evidence={"diagnostic_count": len(environment_diagnostics)},
        ),
    ]
    score = sum(item.points for item in items)
    max_score = sum(item.max_points for item in items)
    blocked = [item.stage for item in items if item.status == "blocked"]
    warnings = [item.stage for item in items if item.status == "warning"]
    readiness = {
        "score": score,
        "max_score": max_score,
        "percent": round((score / max_score) * 100) if max_score else 0,
        "status": "blocked" if blocked else "warning" if warnings else "ready",
        "blocked_stages": blocked,
        "warning_stages": warnings,
    }
    return tuple(items), readiness
