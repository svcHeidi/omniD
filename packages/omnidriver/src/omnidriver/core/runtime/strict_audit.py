from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from omnidriver.core.planning_types import (
    StrictDiagnostic,
    SimulationAuditItem,
    diagnostic,
    has_error,
    has_warning,
)
from .models import DataArtifact

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext  # noqa: F401


#: The operator's switch for declining mesh-scale checks. Renamed from
#: ``SKIP_MESH_DIAGNOSTICS`` 2026-09-26 (spec 2026-09-26 §2, A7): the checks
#: are the plugin's ``*_geometry_diagnostics`` hooks, and "mesh" named one
#: kind of discretisation. The old name is not read.
SKIP_GEOMETRY_DIAGNOSTICS_ENV = "SKIP_GEOMETRY_DIAGNOSTICS"


_READINESS_WEIGHTS = {
    "simulation_generation": 15,
    "case_preparation_files": 15,
    "dictionary_resolution": 20,
    "workflow_preparation": 20,
    "artifact_prediction": 15,
    "environment_preflight": 10,
    "mesh_geometry": 5,
}


#: Outcomes for a stage that did not run, from
#: docs/superpowers/specs/2026-09-18-coverage-as-evidence.md. Each is a distinct
#: fact -- the operator declined the check, it cannot apply to this plan, or the
#: thing it needs was absent -- and all three scored `passed` with full points
#: until 2026-09-18, because every skip path returns an empty diagnostic tuple
#: and an empty tuple has no error and no warning.
UNCOVERED_OUTCOMES = frozenset({"not_requested", "not_applicable", "unavailable"})

#: The stage ran. Its status is then derived from its diagnostics, as before.
EXECUTED = "executed"

#: The one uncovered outcome that leaves the denominator. `not_requested` and
#: `unavailable` are gaps -- work that was owed and not done -- so they stay in
#: and cost the plan its points. `not_applicable` is not a gap: there was
#: nothing to do. Counting it would replace paying for work never done with
#: penalising a plan for work never owed, which is the same defect mirrored.
NOT_APPLICABLE = "not_applicable"


def _score_from_diagnostics(
    *,
    stage: str,
    diagnostics: tuple[StrictDiagnostic, ...],
    success_summary: str,
    warning_summary: str,
    error_summary: str,
    outcome: str,
    uncovered_summary: str = "",
    evidence: dict[str, Any] | None = None,
) -> SimulationAuditItem:
    """Score one stage. ``outcome`` is required and has no default.

    Requiring it is the fix: this function cannot infer from an empty diagnostic
    tuple whether a check ran and found nothing or never ran at all, and for as
    long as it guessed, it guessed success. The caller knows, so the caller says.
    """
    max_points = _READINESS_WEIGHTS[stage]
    if outcome in UNCOVERED_OUTCOMES:
        return SimulationAuditItem(
            stage=stage,
            status=outcome,
            points=0,
            max_points=max_points,
            summary=uncovered_summary or f"{stage} did not run ({outcome}).",
            evidence=evidence or {},
        )
    if outcome != EXECUTED:
        raise ValueError(
            f"{stage}: outcome must be {EXECUTED!r} or one of "
            f"{sorted(UNCOVERED_OUTCOMES)}; got {outcome!r}"
        )
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


def _simulation_generation_audit(spec) -> tuple[SimulationAuditItem, tuple[StrictDiagnostic, ...]]:
    max_points = _READINESS_WEIGHTS["simulation_generation"]
    try:
        cases = spec.build_cases()
    except Exception as exc:
        diag = diagnostic(
            "error",
            "case_generation_failed",
            f"build_cases() failed while creating the simulation list: {exc}",
            source="build_cases",
        )
        return (
            SimulationAuditItem(
                stage="simulation_generation",
                status="blocked",
                points=0,
                max_points=max_points,
                summary="The driver could not create the simulation case list.",
                evidence={"error": str(exc)},
            ),
            (diag,),
        )

    case_ids = [getattr(case, "case_id", "") for case in cases]
    evidence = {
        "case_count": len(cases),
        "case_ids_preview": case_ids[:20],
        "case_ids_truncated": len(case_ids) > 20,
    }
    if not cases:
        diag = diagnostic(
            "error",
            "no_simulations_generated",
            "build_cases() returned no simulations.",
            source="build_cases",
        )
        return (
            SimulationAuditItem(
                stage="simulation_generation",
                status="blocked",
                points=0,
                max_points=max_points,
                summary="The driver did not create any simulations to run.",
                evidence=evidence,
            ),
            (diag,),
        )

    return (
        SimulationAuditItem(
            stage="simulation_generation",
            status="passed",
            points=max_points,
            max_points=max_points,
            summary="build_cases() created the simulation list consumed by the engine.",
            evidence=evidence,
        ),
        (),
    )


def _case_preparation_files_audit(
    case_root: Path,
    *,
    generic_case: bool = False,
    required_files: tuple[str, ...] = (),
) -> SimulationAuditItem:
    max_points = _READINESS_WEIGHTS["case_preparation_files"]
    if generic_case:
        return SimulationAuditItem(
            stage="case_preparation_files",
            status=NOT_APPLICABLE,
            points=0,
            max_points=max_points,
            summary=(
                "Generic case-folder execution relies on its declared workflow "
                "rather than the plugin's dictionary requirements, so there are "
                "no required adapter files to check for."
            ),
            evidence={"case_root": str(case_root), "required": [], "generic_case": True},
        )
    existing = [relpath for relpath in required_files if (case_root / relpath).exists()]
    missing = [relpath for relpath in required_files if not (case_root / relpath).exists()]
    if not missing:
        status = "passed"
        points = max_points
        summary = "The case root already contains the required adapter files."
    elif existing:
        status = "warning"
        points = int(max_points * len(existing) / len(required_files))
        summary = "Some required adapter files are missing before execution."
    else:
        status = "blocked"
        points = 0
        summary = "The case root does not contain required adapter files."
    return SimulationAuditItem(
        stage="case_preparation_files",
        status=status,
        points=points,
        max_points=max_points,
        summary=summary,
        evidence={
            "case_root": str(case_root),
            "required": list(required_files),
            "existing": existing,
            "missing": missing,
        },
    )


def _build_simulation_audit(
    *,
    spec,
    driver_context: "DriverContext",
    workflow_dag: dict[str, Any] | None,
    artifacts: tuple[DataArtifact, ...],
    validation_diagnostics: tuple[StrictDiagnostic, ...],
    workflow_diagnostics: tuple[StrictDiagnostic, ...],
    artifact_diagnostics: tuple[StrictDiagnostic, ...],
    environment_diagnostics: tuple[StrictDiagnostic, ...],
    mesh_geometry_diagnostics: tuple[StrictDiagnostic, ...],
    mesh_geometry_exempt: bool = False,
    required_case_files: tuple[str, ...] = (),
) -> tuple[tuple[SimulationAuditItem, ...], tuple[StrictDiagnostic, ...], dict[str, Any]]:
    generation_item, generation_diagnostics = _simulation_generation_audit(spec)
    generic_case = bool(spec.metadata.get("generic_case")) if spec.metadata else False
    case_files_item = _case_preparation_files_audit(
        Path(spec.case_root),
        generic_case=generic_case,
        required_files=required_case_files,
    )
    items = [
        generation_item,
        case_files_item,
        _score_from_diagnostics(
            stage="dictionary_resolution",
            diagnostics=validation_diagnostics,
            success_summary=(
                "The generic case needs no plugin configuration parsing."
                if generic_case else
                driver_context.capabilities.case_files.describe_config_resolution()
            ),
            warning_summary=(
                "Generic case validation emitted warnings."
                if generic_case else
                "The dictionaries resolve, but validation emitted warnings."
            ),
            error_summary=(
                "The generic case contract could not be resolved."
                if generic_case else
                "The dictionaries could not be resolved into a valid run config."
            ),
            outcome=NOT_APPLICABLE if generic_case else EXECUTED,
            uncovered_summary=(
                "The generic case declares its own workflow and has no plugin "
                "configuration to parse, so there was nothing to resolve."
            ),
            evidence={
                "diagnostic_count": len(validation_diagnostics),
                "generic_case": generic_case,
            },
        ),
        _score_from_diagnostics(
            stage="workflow_preparation",
            diagnostics=workflow_diagnostics,
            success_summary="The workflow DAG is normalized into executable argv-style steps.",
            warning_summary="The workflow DAG is executable, but normalization emitted warnings.",
            error_summary="The workflow DAG is missing or invalid, so strict execution cannot start.",
            outcome=EXECUTED,
            evidence={
                "step_count": 0 if workflow_dag is None else len(workflow_dag.get("steps", ())),
                "step_ids": [] if workflow_dag is None else [
                    str(step.get("id", "")) for step in workflow_dag.get("steps", ())
                ],
            },
        ),
        _score_from_diagnostics(
            stage="artifact_prediction",
            diagnostics=artifact_diagnostics,
            success_summary="The planner predicts raw data artifacts and links them to workflow steps.",
            warning_summary="Artifacts are predicted, but coverage warnings remain.",
            error_summary="The planner cannot reliably predict this run's data artifacts.",
            outcome=EXECUTED,
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
            outcome=(
                "not_requested" if "SKIP_ENV_DIAGNOSTICS" in os.environ else EXECUTED
            ),
            uncovered_summary=(
                "Environment preflight was not requested: SKIP_ENV_DIAGNOSTICS is "
                "set, so nothing was checked about this environment."
            ),
            evidence={
                "skipped": "SKIP_ENV_DIAGNOSTICS" in os.environ,
                "diagnostic_count": len(environment_diagnostics),
            },
        ),
        _score_from_diagnostics(
            stage="mesh_geometry",
            diagnostics=mesh_geometry_diagnostics,
            success_summary="Mesh-scale checks did not find run-preparation issues.",
            warning_summary="Mesh-scale checks emitted warnings.",
            error_summary="Mesh-scale checks found run-preparation issues.",
            # Three ways to arrive with an empty tuple, and they are not the
            # same fact: the operator declined the check, the case has no mesh
            # scale to check, or the mesh was examined and was clean.
            outcome=(
                "not_requested" if SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ
                else NOT_APPLICABLE if mesh_geometry_exempt
                else EXECUTED
            ),
            uncovered_summary=(
                "Mesh-scale checks were not requested: SKIP_GEOMETRY_DIAGNOSTICS is "
                "set, so no mesh geometry was examined."
                if SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ else
                "This entry declares no physical mesh scale, so there is no "
                "mesh geometry to check."
            ),
            evidence={
                "skipped": SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ,
                "exempt": mesh_geometry_exempt,
                "diagnostic_count": len(mesh_geometry_diagnostics),
            },
        ),
    ]
    score = sum(item.points for item in items)
    # The applicable denominator: what this plan actually owed. A
    # `not_applicable` stage owed nothing and is excluded; `not_requested` and
    # `unavailable` owed something and did not deliver, so they stay in and
    # cost the plan its points.
    max_score = sum(
        item.max_points for item in items if item.status != NOT_APPLICABLE
    )
    blocked = [item.stage for item in items if item.status == "blocked"]
    warnings = [item.stage for item in items if item.status == "warning"]
    uncovered = [
        item.stage for item in items
        if item.status in UNCOVERED_OUTCOMES and item.status != NOT_APPLICABLE
    ]
    inapplicable = [item.stage for item in items if item.status == NOT_APPLICABLE]
    readiness = {
        "score": score,
        "max_score": max_score,
        "percent": round((score / max_score) * 100) if max_score else 0,
        # `ready` is a success claim, so a plan with a real coverage gap may not
        # make it. Coverage outranks `warning`: a warning is something a check
        # found, an uncovered stage is a check whose findings nobody has.
        "status": (
            "blocked" if blocked
            else "incomplete" if uncovered
            else "warning" if warnings
            else "ready"
        ),
        "blocked_stages": blocked,
        "warning_stages": warnings,
        "uncovered_stages": uncovered,
        "inapplicable_stages": inapplicable,
    }
    return tuple(items), generation_diagnostics, readiness
