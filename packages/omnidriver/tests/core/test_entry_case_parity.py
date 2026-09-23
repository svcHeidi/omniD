"""`TutorialSpec.plan_case`/`invoke_case_mutation` (Phase 2 Task 10).

Core-level plumbing only: whether the preference-and-fallback policy itself
behaves correctly. It cannot exercise a real migrated spec's byte-level
parity -- every spec migrated so far lives in `omnidriver-cardiaccore`, which
core must not import (see that package's own
`tests/test_entry_case_parity.py` for the byte-level characterization the
plan's Task 10 asks for).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec, invoke_case_mutation


def _spec(**kwargs) -> TutorialSpec:
    defaults = dict(
        name="fake",
        case_root=Path("/tmp/fake-case-root-not-touched"),
        setup_root=Path("/tmp/fake-setup-root-not-touched"),
        output_dir=Path("/tmp/fake-output-dir-not-touched"),
        build_cases=lambda: [CaseConfig(case_id="only", params={})],
        apply_case=lambda case_root, case: None,
    )
    defaults.update(kwargs)
    return TutorialSpec(**defaults)


def test_plan_case_is_optional_and_defaults_to_none():
    spec = _spec()
    assert spec.plan_case is None


def test_invoke_case_mutation_prefers_plan_case_when_present():
    calls = []
    spec = _spec(
        apply_case=lambda case_root, case: calls.append(("apply_case", case_root, case)),
        plan_case=lambda case_root, case: calls.append(("plan_case", case_root, case)) or "a-record",
    )
    case = spec.build_cases()[0]

    result = invoke_case_mutation(spec, spec.case_root, case)

    assert calls == [("plan_case", spec.case_root, case)]
    assert result == "a-record"


def test_invoke_case_mutation_falls_back_to_apply_case_with_a_deprecation_warning():
    calls = []
    spec = _spec(
        apply_case=lambda case_root, case: calls.append(("apply_case", case_root, case)),
    )
    case = spec.build_cases()[0]

    with pytest.warns(DeprecationWarning, match="removed when no in-tree spec supplies apply_case"):
        result = invoke_case_mutation(spec, spec.case_root, case)

    assert calls == [("apply_case", spec.case_root, case)]
    assert result is None


def test_invoke_case_mutation_falling_back_still_returns_none_even_if_apply_case_returns_something():
    """`apply_case`'s declared return type is `None`; a caller relying on
    `invoke_case_mutation`'s return value for a not-yet-migrated spec must
    see `None`, not whatever an ill-behaved `apply_case` happened to return,
    matching `ApplyCaseFn`'s own contract."""
    spec = _spec(apply_case=lambda case_root, case: "not-a-record")
    case = spec.build_cases()[0]

    with pytest.warns(DeprecationWarning):
        result = invoke_case_mutation(spec, spec.case_root, case)

    assert result is None
