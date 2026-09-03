from omnidriver.core.runtime.failure_classification import classify_failure
from omnidriver.core.runtime.workflow_state import WorkflowStepState


def _failed_step(*codes):
    return WorkflowStepState(
        step_id="solve",
        status="failed",
        attempt=1,
        command="cardiacFoam",
        args=(),
        cwd=".",
        exit_code=1,
        diagnostics=tuple({"level": "error", "code": c, "message": "x"} for c in codes),
    )


def test_timeout_is_retryable():
    assert classify_failure(_failed_step("workflow_step_timeout")) == "retryable"


def test_missing_artifacts_is_fatal():
    assert classify_failure(_failed_step("missing_artifacts")) == "fatal"


def test_exec_error_is_fatal():
    assert classify_failure(_failed_step("workflow_step_exec_error")) == "fatal"


def test_generic_failure_no_code_is_fatal():
    assert classify_failure(_failed_step()) == "fatal"


def test_override_forces_fatal_code_to_retryable():
    result = classify_failure(
        _failed_step("missing_artifacts"),
        overrides={"missing_artifacts": "retryable"},
    )
    assert result == "retryable"


def test_override_forces_retryable_code_to_fatal():
    result = classify_failure(
        _failed_step("workflow_step_timeout"),
        overrides={"workflow_step_timeout": "fatal"},
    )
    assert result == "fatal"
