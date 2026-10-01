"""What one solver hands the conformance suite, and what each check returns.

Everything here is supplied by the caller; the suite discovers nothing.
See docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.specs.paths import resolve_scratch_root


@dataclass(frozen=True)
class QuantityTarget:
    """A quantity a record's run yields, and what C13 and C14 compare.

    ``study`` overlays the target's ``base_study`` for those runs, so the
    quantity occurs (an end time past the slowest activation). ``at`` is where
    each named quantity is sampled, or expected, in ``at_unit``, in the
    solver's own frame; ``pairs`` names, for each label of the point
    ``reference``, the quantity that answers it. The tolerances are the
    solver's own physics: ``parallel_tolerance`` bounds, in the reader's unit,
    how far a parallel run may sit from the serial one; ``tolerance`` is the
    declared bound of C14's comparison, in ``tolerance_unit``.
    ``parallel_study`` adds what a parallel run needs beyond ``parallel: ranks``.
    """

    artifact_format: str
    reference: Path
    pairs: Mapping[str, str]
    at: Mapping[str, tuple[float, float, float]]
    at_unit: str
    max_sampling_offset: float
    study: Mapping[str, Any]
    sweep_values: tuple[Any, Any]
    tolerance: float
    tolerance_unit: str
    parallel_tolerance: float
    parallel_study: Mapping[str, Any] = field(default_factory=dict)
    ranks: int = 2
    both_not_reached: str = "agree"


@dataclass(frozen=True)
class ConformanceTarget:
    """One solver record, and the study values that exercise it.

    ``scratch_root`` receives every stage, plan and sweep; the native tree
    under ``cases_root`` is never written. ``base_study`` pins values (e.g.
    mesh resolution, time step) that keep a real run short. ``quantity``,
    when declared, is what C13 and C14 compare; without it they have nothing
    to compare and pass saying so.
    """

    plugin: str
    record: str
    cases_root: Path
    scratch_root: Path
    base_study: Mapping[str, Any]
    patch: tuple[str, Any]
    untouched: tuple[str, tuple[str, ...]]
    sweep_name: str
    sweep_values: tuple[Any, Any]
    unknown_name: str
    #: Every ``--input NAME=PATH`` this record's own inputs need, forwarded
    #: to every plan/run/sweep a check makes (C5-C7) and to a direct
    #: ``commit_record_case`` call (C4, C11). Empty for a record with no
    #: inputs, or one whose inputs all have a native location.
    inputs: Mapping[str, str] = field(default_factory=dict)
    #: Wall-clock bound, in seconds, on each child process a check starts
    #: (C6's run, C7's sweep-run) and on each sweep case (``sweep-run
    #: --case-timeout-s``). A child that outlives it is a failed verdict
    #: naming the timeout, never a check that does not return.
    timeout_s: float = 600.0
    quantity: QuantityTarget | None = None

    def __post_init__(self) -> None:
        # scratch_root must be distinct from cases_root so nothing a check
        # stages lands inside the native tree; delegates to core's own rule
        # (resolve_scratch_root) rather than duplicating it here.
        resolve_scratch_root(self.scratch_root, cases_root=self.cases_root)


@dataclass(frozen=True)
class CheckVerdict:
    check_id: str
    passed: bool
    detail: str
