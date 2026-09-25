"""What one solver hands the conformance suite, and what each check returns.

Design: docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md §4.
Everything here is supplied by the caller; the suite discovers nothing
(future/ENVIRONMENT_CONTRACT.md §12).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ConformanceTarget:
    """One solver record, and the study values that exercise it.

    ``environment`` is an overlay on the calling process's environment for
    every child process a check starts. ``scratch_root`` receives every
    stage, plan and sweep: the native tree under ``cases_root`` is never
    written. ``base_study`` pins values that keep a real run short (for
    openCARP, mesh resolution and time step; evidence G7).
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


@dataclass(frozen=True)
class CheckVerdict:
    check_id: str
    passed: bool
    detail: str
