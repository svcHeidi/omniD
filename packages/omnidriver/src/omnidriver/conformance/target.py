"""What one solver hands the conformance suite, and what each check returns.

Everything here is supplied by the caller; the suite discovers nothing.
See docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from omnidriver.core.conformance_study import ConformanceStudy
from omnidriver.core.specs.paths import resolve_scratch_root


@dataclass(frozen=True, kw_only=True)
class ConformanceTarget(ConformanceStudy):
    """One solver record's study, placed: ``scratch_root`` receives every
    stage, plan and sweep, and the native tree under ``cases_root`` is never
    written. ``inputs`` is every ``--input NAME=PATH`` the record's own inputs
    need, forwarded to every plan/run/sweep a check makes (C5-C7) and to a
    direct ``commit_record_case`` call (C4, C11); empty for a record with no
    inputs, or one whose inputs all have a native location.
    """

    plugin: str
    record: str
    cases_root: Path
    scratch_root: Path
    inputs: Mapping[str, str] = field(default_factory=dict)

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
