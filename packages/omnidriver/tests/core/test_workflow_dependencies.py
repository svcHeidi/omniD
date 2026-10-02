"""A workflow step may depend only on another step of the same DAG."""
from __future__ import annotations

from omnidriver.core.runtime.workflow import normalize_workflow_dag


def _codes(steps):
    _dag, diagnostics = normalize_workflow_dag({"steps": steps}, driver_context=None)
    return [(item.code, item.field) for item in diagnostics if item.level == "error"]


def test_a_dependency_on_a_step_the_dag_does_not_hold_is_refused_by_name():
    assert _codes([
        {"id": "mesh", "command": "blockMesh"},
        {"id": "solve", "command": "solver", "depends_on": ["meshh"]},
    ]) == [("unknown_workflow_dependency", "solve")]


def test_a_step_depending_on_itself_is_not_also_called_unknown():
    codes = [code for code, _field in _codes([{"id": "solve", "command": "solver", "depends_on": ["solve"]}])]
    assert "workflow_step_self_dependency" in codes and "unknown_workflow_dependency" not in codes


def test_dependencies_on_known_steps_are_accepted():
    assert _codes([
        {"id": "mesh", "command": "blockMesh"},
        {"id": "solve", "command": "solver", "depends_on": ["mesh"]},
    ]) == []
