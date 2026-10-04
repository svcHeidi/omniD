"""Neutral path resolver for ``strict_plan``, taking the already-built ``TutorialSpec``.

It re-resolves no entry and does not depend on the CLI's action vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

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
    #: The plan-time coverage audit, when the caller has one; always empty for
    #: a RunDocument-based execution, since schemas/run-document.json carries
    #: no such field -- is_launchable must see "unavailable", not nothing.
    simulation_audit: tuple[SimulationAuditItem, ...] = ()
    execution_env: dict[str, str] | None = None
    source_path: str | None = None
    driver_context: "DriverContext | None" = None
    #: Edit the case with ``document:key`` patches, rolling the edit back when
    #: the check it is given (the replan) refuses; both are ``None`` for a
    #: plan that has no record case to edit.
    apply_study: Callable[[Mapping[str, Any], Callable[[], None]], tuple[dict[str, Any], ...]] | None = None
    replan_after_mutation: Callable[[], ReplannedExecution] | None = None


def resolve_execution_context(spec: TutorialSpec) -> ExecutionContext:
    output_dir = Path(spec.metadata["output_dir"])
    return ExecutionContext(
        case_root=Path(spec.case_root),
        setup_root=Path(spec.metadata["setup_root"]),
        output_dir=output_dir,
        workflow_state_path=output_dir / STATE_FILENAME,
    )
