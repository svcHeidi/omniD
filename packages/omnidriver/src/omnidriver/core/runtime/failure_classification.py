from __future__ import annotations

# workflow_step_timeout is the canonical transient failure (load/contention).
# Everything else is deterministic by default: missing_artifacts (command
# "succeeded" but produced nothing), workflow_step_exec_error (could not
# launch), and generic nonzero exit (FOAM FATAL ERROR, divergence).
RETRYABLE_CODES = frozenset({"workflow_step_timeout"})


def classify_failure(step_state) -> str:
    """Return "retryable" or "fatal" for a failed step."""
    for diagnostic in step_state.diagnostics:
        if diagnostic.get("code") in RETRYABLE_CODES:
            return "retryable"
    return "fatal"
