"""A required check that could not run must block the launch it covers."""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from omnidriver.core.planning_types import SimulationAuditItem
from omnidriver.core.runtime.launch_readiness import is_launchable


def test_an_unavailable_required_check_blocks():
    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(
            SimulationAuditItem(
                stage="effective_configuration", status="unavailable",
                points=0, max_points=10, summary="x", evidence={},
            ),
        ),
    )
    assert not readiness.launchable
    assert not readiness.coverage_ok
    assert "effective_configuration" in readiness.blocking_reason


def test_omitting_the_audit_still_never_blocks():
    """Offline planning must keep working with no runtime installed."""
    assert is_launchable(plan_status="ok").launchable


def test_the_dispatch_gate_receives_the_audit(tmp_path: Path):
    """The half that was missing: the predicate was correct and unfed."""
    from omnidriver import cli

    case_root = tmp_path / "case"
    case_root.mkdir()
    unavailable_item = SimulationAuditItem(
        stage="artifact_prediction", status="unavailable",
        points=0, max_points=20, summary="could not run", evidence={},
    )
    report = SimpleNamespace(
        status="ok",
        environment_diagnostics=(),
        simulation_audit=(unavailable_item,),
        workflow_dag={"steps": []},
        workflow_state=SimpleNamespace(),
        launch={
            "case_root": str(case_root),
            "output_dir": str(tmp_path / "output"),
            "setup_root": str(tmp_path / "setup"),
        },
        expected_artifacts=(),
    )
    driver_context = SimpleNamespace(stack=SimpleNamespace(call=lambda member, *_args, **_kwargs: {}))

    with mock.patch.object(cli, "strict_plan", return_value=report):
        execution, code = cli._context_from_entry(
            selected_entry="someEntry",
            overrides=None,
            environment_source=None,
            driver_context=driver_context,
        )

    assert code == 0
    assert execution is not None
    # The context genuinely carries the unavailable stage -- not a fixture
    # asserting the wiring exists, but the wiring producing it.
    assert execution.simulation_audit == (unavailable_item,)

    blocked = cli._refuse_environment_errors(execution, action="run")
    assert blocked == 1, (
        "a dispatch context whose plan-time audit reports an unavailable "
        "required check must be refused, not launched"
    )


def test_an_available_audit_does_not_block_on_coverage_alone(tmp_path: Path):
    """Symmetry check: a clean audit must not spuriously block dispatch."""
    from omnidriver import cli

    case_root = tmp_path / "case2"
    case_root.mkdir()
    report = SimpleNamespace(
        status="ok",
        environment_diagnostics=(),
        simulation_audit=(
            SimulationAuditItem(
                stage="artifact_prediction", status="passed",
                points=20, max_points=20, summary="ok", evidence={},
            ),
        ),
        workflow_dag={"steps": []},
        workflow_state=SimpleNamespace(),
        launch={
            "case_root": str(case_root),
            "output_dir": str(tmp_path / "output2"),
            "setup_root": str(tmp_path / "setup2"),
        },
        expected_artifacts=(),
    )
    driver_context = SimpleNamespace(stack=SimpleNamespace(call=lambda member, *_args, **_kwargs: {}))

    with mock.patch.object(cli, "strict_plan", return_value=report):
        execution, code = cli._context_from_entry(
            selected_entry="someEntry",
            overrides=None,
            environment_source=None,
            driver_context=driver_context,
        )

    assert code == 0
    assert execution is not None
    assert cli._refuse_environment_errors(execution, action="run") is None
