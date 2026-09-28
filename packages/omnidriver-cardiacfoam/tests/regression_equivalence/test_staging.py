"""Agent addressability of every regression case (solver-free)."""
from __future__ import annotations

import pytest
from conftest import skip_without_monorepo
pytestmark = skip_without_monorepo

from regression_equivalence.registry import REGRESSION_CASES
from regression_equivalence.staging import (
    resolve_generic,
    resolve_strict,
)

ADDRESSABLE = [c for c in REGRESSION_CASES if c.generic_addressable]
NOT_ADDRESSABLE = [c for c in REGRESSION_CASES if not c.generic_addressable]
MAPPED = [c for c in REGRESSION_CASES if c.mapped]


@pytest.mark.parametrize("case", ADDRESSABLE, ids=lambda c: c.case_dir)
def test_generic_path_resolves(case):
    resolution = resolve_generic(case)
    assert resolution["resolution"] == "case_folder", case.case_dir
    assert resolution["is_runnable"] is True, case.case_dir


# NOT_ADDRESSABLE is empty today; pytest's empty-parametrize skip is expected, not an environment gate.
@pytest.mark.parametrize("case", NOT_ADDRESSABLE, ids=lambda c: c.case_dir)
def test_non_addressable_case_is_not_discoverable(case):
    with pytest.raises(KeyError, match="Unknown entry"):
        resolve_generic(case)


@pytest.mark.parametrize("case", MAPPED, ids=lambda c: c.entry_name)
def test_mapped_entry_resolves_registered(case):
    """Each mapped case resolves to its own ``case.resolution`` (``registered`` or ``tutorial_record``)."""
    resolution = resolve_strict(case)
    assert resolution["resolution"] == case.resolution, case.entry_name
    assert resolution["is_runnable"] is True, case.entry_name
