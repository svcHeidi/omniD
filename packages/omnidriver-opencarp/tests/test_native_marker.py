"""openCARP's native tests carry their own marker, never cardiacFOAM's
(final review S-I1, 2026-09-25).

``native`` means "the cardiacFOAM native tree" (OMNIDRIVER_NATIVE_TUTORIALS):
CLAUDE.md's ``packages/ -m native`` row runs it repo-wide. openCARP's native
tests need a different tree and the real binary, and FAIL (not skip) without
them, so under the shared marker that row reported openCARP failures that had
nothing to do with cardiacFOAM. They are ``native_opencarp`` instead."""
from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
_SHARED = re.compile(r"pytest\.mark\.native\b(?!_)")


def test_no_opencarp_test_carries_the_cardiacfoam_native_marker():
    offenders = [p.name for p in sorted(TESTS.glob("*.py")) if p.name != Path(__file__).name
                 and _SHARED.search(p.read_text())]
    assert offenders == []


def test_every_native_module_carries_the_opencarp_marker():
    unmarked = [p.name for p in sorted(TESTS.glob("test_*_native.py"))
                if "pytestmark = pytest.mark.native_opencarp" not in p.read_text()]
    assert unmarked == []
    assert sorted(TESTS.glob("test_*_native.py")), "no native module found"
