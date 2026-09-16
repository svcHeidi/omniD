"""Resolve execution paths from an already constructed ``TutorialSpec``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .models import TutorialSpec

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
        workflow_state_path=output_dir / "workflow_state.json",
    )
