from __future__ import annotations

# workflow_step_timeout is the canonical transient failure (load/contention).
# Everything else is deterministic by default: missing_artifacts (command
# "succeeded" but produced nothing), workflow_step_exec_error (could not
# launch), and generic nonzero exit (FOAM FATAL ERROR, divergence).
RETRYABLE_CODES = frozenset({"workflow_step_timeout"})


def classify_failure(step_state, *, overrides: dict[str, str] | None = None) -> str:
    """Return "retryable" or "fatal" for a failed step.

    overrides maps a diagnostic code to a forced classification — the extension
    seam for problem #3 / agent reclassification. The mechanical retry path
    never populates it.
    """
    overrides = overrides or {}
    for diagnostic in step_state.diagnostics:
        code = diagnostic.get("code")
        if code in overrides:
            return overrides[code]
        if code in RETRYABLE_CODES:
            return "retryable"
    return "fatal"
