from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RemediationHint:
    diagnostic_code: str
    driver_path: str   # "" => advisory (no mutation)
    change: str        # human-readable transform; descriptive, never executed by the driver
    rationale: str
    source: str        # "static"
    confidence: str    # "high" | "low"

    def to_json(self) -> dict[str, Any]:
        return {
            "diagnostic_code": self.diagnostic_code,
            "driver_path": self.driver_path,
            "change": self.change,
            "rationale": self.rationale,
            "source": self.source,
            "confidence": self.confidence,
        }


# Static, diagnostic-code-keyed hints. Advisory only (empty driver_path) — these
# failures are not fixed by a catalog mutation.
STATIC_REMEDIATION_HINTS: dict[str, tuple[RemediationHint, ...]] = {
    "missing_artifacts": (
        RemediationHint(
            diagnostic_code="missing_artifacts",
            driver_path="",
            change="",
            rationale=(
                "The command reported success but produced no expected artifact. "
                "Verify the producing utility/pre-solve step actually ran and wrote output."
            ),
            source="static",
            confidence="low",
        ),
    ),
    "workflow_step_exec_error": (
        RemediationHint(
            diagnostic_code="workflow_step_exec_error",
            driver_path="",
            change="",
            rationale=(
                "The step command could not be launched. Check the executable is on PATH "
                "and the OpenFOAM environment is sourced."
            ),
            source="static",
            confidence="low",
        ),
    ),
}


def _static_hints(failure_context: dict[str, Any]) -> tuple[RemediationHint, ...]:
    out: list[RemediationHint] = []
    for diagnostic in failure_context.get("diagnostics", ()):
        code = diagnostic.get("code")
        out.extend(STATIC_REMEDIATION_HINTS.get(code, ()))
    return tuple(out)





def build_candidate_remediations(failure_context: dict[str, Any]) -> tuple[RemediationHint, ...]:
    """Suggestion-only remediation ladder. Never raises; returns () on any problem.

    Only static, diagnostic-code-keyed hints are emitted. There is no reactive
    log-signature layer: the driver does not guess numerical fixes (e.g. halving
    deltaT on divergence) from log tails. Correct per-ODE deltaT is chosen up
    front from the catalog's typical values, not repaired after the fact.
    """
    try:
        # Exact diagnostic code matches from the structured catalog.
        hints = _static_hints(failure_context)
        if hints:
            return hints

        # No structured hint found; return empty so the agent can reason.
        return ()
    except Exception:
        return ()
