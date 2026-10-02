from __future__ import annotations

from pathlib import Path

from omnidriver.core.runtime.execution_context import resolve_execution_context
from omnidriver.core.runtime.models import TutorialSpec


def test_reports_case_setup_output_and_workflow_state_paths(tmp_path: Path) -> None:
    spec = TutorialSpec(
        name="toy", case_root=tmp_path / "case",
        metadata={"setup_root": str(tmp_path / "case"), "output_dir": str(tmp_path / "case")},
    )

    context = resolve_execution_context(spec)

    assert context.case_root == tmp_path / "case"
    assert context.setup_root == tmp_path / "case"
    assert context.output_dir == tmp_path / "case"
    assert context.workflow_state_path == tmp_path / "case" / "workflow_state.json"
