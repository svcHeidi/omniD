"""A required check that could not run must block the launch it covers.

`is_launchable` has modelled this since 2026-09-19 and its own docstring
recorded that nothing supplied `simulation_audit`, so `coverage_ok` was always
True at the gate. An introspection field that always says yes is worse than no
field: it reads as a guarantee.

Phase 2 makes post-write effective-value readback a required check. If an
unavailable check cannot block, a write whose result could not be verified
dispatches anyway.

Wired 2026-09-22 (audit finding C2): `StepExecutionContext` now carries
`simulation_audit`, and `cli._refuse_environment_errors` -- the one
dispatch-time gate -- passes it to `is_launchable`. The behavioural test below
drives that path for real: it builds a dispatch context the way
`cli._context_from_entry` does (from a stubbed `strict_plan` report carrying an
`unavailable` stage) and confirms the dispatch-time gate refuses it, rather
than inspecting `cli`'s source text for the keyword.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

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


@pytest.mark.parametrize("status", ["not_requested", "not_applicable"])
def test_a_declined_or_inapplicable_check_does_not_block(status):
    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(
            SimulationAuditItem(
                stage="scientific", status=status,
                points=0, max_points=10, summary="x", evidence={},
            ),
        ),
    )
    assert readiness.launchable


def test_omitting_the_audit_still_never_blocks():
    """Offline planning must keep working with no runtime installed."""
    assert is_launchable(plan_status="ok").launchable


def test_the_dispatch_gate_receives_the_audit(tmp_path: Path):
    """The half that was missing: the predicate was correct and unfed.

    Drives `cli._context_from_entry` -- the real producer of a dispatch-time
    `StepExecutionContext` -- with a stubbed `strict_plan()` report whose
    `simulation_audit` carries a genuinely `unavailable` stage, then calls
    `cli._refuse_environment_errors` -- the real dispatch-time gate -- on the
    context it built. `is_launchable` is not mocked anywhere in this test: if
    the audit were dropped anywhere along the way (as it was before this
    fix), this test would see `blocked is None` and fail.
    """
    from omnidriver import cli

    case_root = tmp_path / "case"
    case_root.mkdir()
    unavailable_item = SimulationAuditItem(
        stage="dictionary_resolution", status="unavailable",
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
    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            environment_preflight=SimpleNamespace(load=lambda **_kwargs: {}),
        )
    )

    with mock.patch.object(cli, "strict_plan", return_value=report), \
         mock.patch.object(cli, "repo_root_or_none", return_value=None):
        execution, code = cli._context_from_entry(
            selected_entry="someEntry",
            entry_kind=None,
            overrides=None,
            config_path=None,
            explicit_bashrc=None,
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
                stage="dictionary_resolution", status="passed",
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
    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            environment_preflight=SimpleNamespace(load=lambda **_kwargs: {}),
        )
    )

    with mock.patch.object(cli, "strict_plan", return_value=report), \
         mock.patch.object(cli, "repo_root_or_none", return_value=None):
        execution, code = cli._context_from_entry(
            selected_entry="someEntry",
            entry_kind=None,
            overrides=None,
            config_path=None,
            explicit_bashrc=None,
            driver_context=driver_context,
        )

    assert code == 0
    assert execution is not None
    assert cli._refuse_environment_errors(execution, action="run") is None
