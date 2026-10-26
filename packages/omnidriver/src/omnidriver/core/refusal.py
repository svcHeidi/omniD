"""The one shape in which a command is refused: ``{"status": "failed", "code": ..., "error": ...}`` on stdout, exit 1.

``code`` is one of :data:`CODES`. A refusal that knows which rules a value broke also carries ``refusals``, the
plan diagnostics behind it as data (``level``, ``code``, ``message``, ``source``, ``field``, ``detail``).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any, Sequence


#: Every ``code`` a refusal reports, and what it means.
CODES: dict[str, str] = {
    "usage": "a command-line flag or argument is wrong or missing",
    "unknown_record": "no record of the stack has the --entry name",
    "unknown_key": "a study key the solver's catalogue does not declare and its C++ does not read there",
    "unknown_document": "a study key names a document the solver does not read",
    "catalog_rule": "a study value breaks its catalogue entry's rule (refusals[].detail.rule)",
    "axis_rule": "an axis value breaks the axis's kind, bound or menu, or the axis refused it",
    "case_rule": "the resolved case breaks the stack's case rules (one refusal per rule)",
    "shadowed_key": "a study key spells, as a pattern, a key its document already holds literally, so the solver would never read it",
    "cases_failed": "a sweep ran or planned, and at least one case failed; each case carries its own code",
    "cases_blocked": "a sweep planned, and every case that is not ok is blocked (a valid plan whose environment is not ready)",
    "benchmark_unreadable": "a --benchmarks reference could not be read or is not a point reference",
    "scratch_root_not_supplied": "an operation that stages needs --scratch-dir or OMNIDRIVER_SCRATCH_DIR",
    "scratch_root_inside_cases_root": "the supplied scratch root lies inside the cases root",
    "lease_held": "another attempt owns the case or output directory",
    "spec_unreadable": "the sweep spec is not readable JSON",
    "plan_failed": "the case's strict plan has an error diagnostic",
    "plan_blocked": "the case's strict plan is blocked",
    "plan_incomplete": "the strict plan produced no workflow to run",
    "allocation_mismatch": "a run document's MPI process count differs from the scheduler allocation it is run in",
    "environment_preflight_failed": "the execution environment failed its preflight",
    "required_check_unavailable": "a check the run requires could not run",
    "run_document_unreadable": "the run document could not be loaded",
    "run_document_plugin_mismatch": "the run document was planned by another stack",
    "run_document_invalid": "the run document fails validation (diagnostics)",
    "workflow_state_failed": "the workflow state is failed; rerun a step explicitly",
    "workflow_without_current_step": "the workflow is pending but names no current step",
    "attempts_exhausted": "the maximum total step attempts was reached",
    "fresh_would_delete_case": "--fresh would delete the case itself",
    "fresh_refused": "--fresh could not empty the output directory",
    "case_edit_interrupted": "an earlier edit of the case was interrupted; plan again",
    "cxx_source_undeclared": "the stack declares no C++ source to scan",
    "cxx_source_not_scanned": "the C++ source could not be scanned",
    "build_products_undeclared": "the stack lists no build of the repository that only a build record can identify",
    "nothing_built": "the stack lists builds of the repository but none exists where the environment says it is built; run in the solver's shell after building",
    "run_without_report": "a child run exited without a JSON report",
    "case_timeout": "a sweep case exceeded --case-timeout-s",
    "sweep_stopped": "a signal stopped the sweep",
    "unknown_problem": "a problem library holds no problem of that id",
    "problem_invalid": "a problem definition breaks its library's schema",
    "results_invalid": "a solver's results for a verification problem are malformed, repeat a level or give a field at only some levels",
    "non_finite_values": "a field to be compared holds a NaN or an infinity, so it has no error norm",
    "errors_unusable": "an error that is not finite and positive has no convergence order",
    "spacings_unusable": "a grid spacing that is not finite, positive and successively distinct has no convergence order",
    "weights_invalid": "the weights of an error norm cannot be built from the grid or elements given",
    "internal_error": "an unexpected exception: a defect in omniD or a plugin, not in the request",
    "unclassified": "a refusal that names no code of its own; read error",
}


class Refusal(Exception):
    """A command the caller got wrong; its message is the ``error``."""

    code = "usage"


class RefusingParser(argparse.ArgumentParser):
    """An argument parser whose usage errors are :class:`Refusal` (``--help`` stays argparse's own)."""

    def error(self, message: str):
        raise Refusal(message)


def refusal_code(exc: BaseException | None) -> str:
    """``exc``'s own named code, else ``unclassified``."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else "unclassified"


def caught_code(exc: BaseException) -> str:
    """The code of what a catch-all caught: a refusal (a :class:`Refusal`, ``ValueError`` or ``OSError``) keeps its
    own, and anything else is a crash, ``internal_error``."""
    return refusal_code(exc) if isinstance(exc, (Refusal, ValueError, OSError)) else "internal_error"


def failure(
    exc: BaseException | None, *, code: str | None = None, error: str | None = None,
    broken: Sequence[Any] | None = None, **extra: Any,
) -> dict[str, Any]:
    """The refusal payload for ``exc``, or for a refusal with no exception (``code`` and ``error`` given).
    ``refusals`` are the ``broken`` diagnostics, else the ones ``exc`` carries."""
    refusals = [asdict(item) for item in (getattr(exc, "diagnostics", ()) if broken is None else broken)]
    return {
        "status": "failed", **extra, "code": code or refusal_code(exc), **({"refusals": refusals} if refusals else {}),
        "error": str(exc) if error is None else error,
    }


def print_refusal(refusal: BaseException, **extra: Any) -> int:
    print(json.dumps(failure(refusal, **extra), indent=2))
    return 1
