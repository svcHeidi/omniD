import os
import re
import pytest
from pathlib import Path

os.environ["SKIP_ENV_DIAGNOSTICS"] = "1"


from omnidriver.core.specs.paths import cardiacfoam_monorepo_root

#: The monorepo root resolved once at collection time.  ``None`` in standalone.
#: Shared with shipped code (e.g. utility_catalog.py's UTILITIES_ROOT) via
#: cardiacfoam_monorepo_root() rather than each conftest.py recomputing its
#: own copy of the same walk-up search.
monorepo_root: Path | None = cardiacfoam_monorepo_root()

#: Apply this decorator to any test class/function that reads real tutorial
#: case directories from the monorepo ``tutorials/`` tree.  The test is
#: automatically skipped in standalone clones and CI environments.
skip_without_monorepo = pytest.mark.skipif(
    monorepo_root is None,
    reason=(
        "Requires the full cardiacFoam monorepo tree (tutorials/ + applications/). "
        "Clone the full repository or run with --tutorials-root to enable this test."
    ),
)


def _foam_tokens(value: str) -> list[str]:
    """Split an OpenFOAM value into tokens, with brackets as their own."""
    return re.findall(r"[()\[\]]|[^\s()\[\]]+", value)


def foam_values_equal(actual: str, expected: str) -> bool:
    """Compare two OpenFOAM values ignoring how they were spelled.

    A dict written by the real ``foamDictionary`` and one written by the
    pure-Python fallback carry the same values in different text: bracket
    padding (``[-1 0]`` vs ``[ -1 0 ]``) and numeric spelling (``2e-5`` vs
    ``2e-05``) both differ. Assertions that care about the value, not the
    spelling, should use this so they hold in either environment.
    """
    actual_tokens, expected_tokens = _foam_tokens(actual), _foam_tokens(expected)
    if len(actual_tokens) != len(expected_tokens):
        return False
    for got, want in zip(actual_tokens, expected_tokens):
        if got == want:
            continue
        try:
            if float(got) == float(want):
                continue
        except ValueError:
            pass
        return False
    return True


def assert_foam_entry(path, key, expected, *, scope=None) -> None:
    """Assert that ``key`` resolves to ``expected``, whatever its spelling."""
    from omnidriver.openfoam.mutators import read_foam_entry

    actual = read_foam_entry(Path(path), key, scope=scope)
    assert actual is not None, f"{key!r} not found (scope={scope!r}) in {path}"
    assert foam_values_equal(actual, expected), (
        f"{key!r} (scope={scope!r}) is {actual!r}, expected {expected!r}"
    )
