"""What one solver hands the conformance suite, and what each check returns.

Design: docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md §4.
Everything here is supplied by the caller; the suite discovers nothing
(future/ENVIRONMENT_CONTRACT.md §12).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.specs.paths import resolve_scratch_root


@dataclass(frozen=True)
class ConformanceTarget:
    """One solver record, and the study values that exercise it.

    ``environment`` is an overlay on the calling process's environment for
    every child process a check starts. ``scratch_root`` receives every
    stage, plan and sweep: the native tree under ``cases_root`` is never
    written. ``base_study`` pins values that keep a real run short (for
    openCARP, mesh resolution and time step; evidence G7).

    Corrected 2026-09-26: this said checks are not thread-parallel within one
    process, because in-process planning took core's scratch root from the
    process environment. Every check now passes ``scratch_root`` explicitly
    (``strict_plan(scratch_root=...)``, ``--scratch-dir``, a child's own env
    dict), and none writes ``os.environ``.
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
    solver_command: str
    environment: Mapping[str, str]
    #: Wall-clock bound, in seconds, on each child process a check starts
    #: (C6's run, C7's sweep-run) and on each sweep case (``sweep-run
    #: --case-timeout-s``). A child that outlives it is a failed verdict
    #: naming the timeout, never a check that does not return (fix round 1
    #: I5, 2026-09-25).
    timeout_s: float = 600.0

    def __post_init__(self) -> None:
        # M8 (fix round 1, 2026-09-25): every stage, plan and rmtree a check
        # makes lands under scratch_root, so one inside cases_root would do
        # all of it inside the native tree. Since 2026-09-26 this is core's
        # own rule (`resolve_scratch_root`), not a second copy of it.
        resolve_scratch_root(self.scratch_root, cases_root=self.cases_root)


@dataclass(frozen=True)
class CheckVerdict:
    check_id: str
    passed: bool
    detail: str
