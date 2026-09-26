"""Neutral path resolver for strict_plan().

strict_plan() used to call describe_launch("sim", entry, ...) purely to get
these four paths -- that re-resolved the entry (resolve_entry + factory) a
second time (strict_plan already has the spec from load_entry_spec) and,
worse, coupled the strict/workflow-DAG execution path (which never runs the
legacy sim/post/all CLI) to describe_launch's VALID_DRIVER_ACTIONS vocabulary.
This module takes the already-built TutorialSpec directly: no re-resolution,
no action string, no dependency on which CLI actions happen to exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from ..planning_types import SimulationAuditItem
from .models import TutorialSpec
from .workflow_orchestrator import STATE_FILENAME

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext
    from ..strict_planning import StrictDiagnostic


@dataclass(frozen=True)
class ExecutionContext:
    case_root: Path
    setup_root: Path
    output_dir: Path
    workflow_state_path: Path


@dataclass(frozen=True)
class ReplannedExecution:
    """A newly validated execution plan produced after case mutation."""

    workflow_dag: dict[str, Any]
    planned_state: object
    expected_artifacts: tuple[Any, ...]


@dataclass(frozen=True)
class StepExecutionContext:
    """Solver-neutral inputs needed to validate and dispatch one workflow step."""

    entry_label: str
    workflow_dag: dict[str, Any]
    planned_state: object
    case_root: Path
    output_dir: Path
    expected_artifacts: tuple[Any, ...]
    setup_root: Path | None = None
    environment_diagnostics: tuple["StrictDiagnostic", ...] = ()
    #: The plan-time coverage audit, when the caller has one. Populated from
    #: ``StrictPlanReport.simulation_audit`` for an entry-based plan
    #: (``cli._context_from_entry``); always empty for a RunDocument-based
    #: execution (``cli._context_from_run_document``), because a RunDocument
    #: carries no plan-time audit today -- ``schemas/run-document.json`` has
    #: no such field. Added 2026-09-22 (audit finding C2) so the dispatch-time
    #: ``is_launchable`` gate can see a required check that came back
    #: ``unavailable``, rather than checking a value nobody supplied.
    simulation_audit: tuple[SimulationAuditItem, ...] = ()
    execution_env: dict[str, str] | None = None
    source_path: str | None = None
    driver_context: "DriverContext | None" = None
    replan_after_mutation: Callable[[], ReplannedExecution] | None = None


def resolve_execution_context(spec: TutorialSpec) -> ExecutionContext:
    output_dir = Path(spec.output_dir)
    return ExecutionContext(
        case_root=Path(spec.case_root),
        setup_root=Path(spec.setup_root),
        output_dir=output_dir,
        workflow_state_path=output_dir / STATE_FILENAME,
    )
