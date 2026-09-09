"""Opt-in T7 execution gate for a manifest-selected cardiacFoam case."""

from __future__ import annotations

from pathlib import Path

import pytest

from selected_cardiacfoam_fixture import (
    FixtureInputError,
    selected_runtime_from_environment,
    selected_source_from_environment,
)
from selected_cardiacfoam_integration import (
    load_integration_commands,
    run_selected_integration,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
def test_selected_driver_run_and_solver_checker() -> None:
    """Run only an explicitly named disposable fixture; never discover one."""
    source = selected_source_from_environment()
    try:
        runtime = selected_runtime_from_environment(
            source, repository_root=_REPOSITORY_ROOT
        )
    except FixtureInputError:
        # Selected-but-invalid inputs must be a failure, not a native skip.
        raise
    if runtime is None:
        pytest.skip("selected-runtime fixture was not requested")

    evidence = run_selected_integration(runtime, load_integration_commands(runtime))

    assert evidence.driver.returncode == 0, evidence.driver.tail
    assert not evidence.driver.timed_out
    # The solver owns this command and any numerical thresholds it applies.
    assert evidence.solver_checker.returncode == 0, evidence.solver_checker.tail
    assert not evidence.solver_checker.timed_out
    assert evidence.evidence_path.is_file()
