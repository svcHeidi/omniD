import os
import re
import pytest
from pathlib import Path

os.environ["SKIP_ENV_DIAGNOSTICS"] = "1"


from omnidriver.core.specs.paths import cardiacfoam_monorepo_root, repo_root_default


def _repo_root_or_none() -> Path | None:
    """The repository root, or ``None`` when there is no checkout.

    ``repo_root_default()`` raises rather than guessing, which is right for
    runtime code -- silently resolving to the wrong ancestor is worse than
    failing. But a *test module* that calls it at import time turns "no
    checkout" into a collection error, which no skipif marker can catch
    because the module never finishes importing. Eight modules did exactly
    that, so `pytest packages/omnidriver/tests` could not even be collected
    against an installed wheel; see scripts/check-wheel-artifact.py.
    """
    try:
        return repo_root_default()
    except RuntimeError:
        return None


#: The repository root resolved once at collection time. ``None`` when running
#: against an installed distribution with no checkout above it.
repo_root: Path | None = _repo_root_or_none()

#: Stand-in so a module-level ``REPO_ROOT / "schemas" / ...`` expression stays
#: constructible when there is no checkout. Building a Path touches no
#: filesystem; every test that would dereference it is skipped by
#: ``skip_without_repo``, so this value is never read.
NO_REPO_ROOT = Path("/nonexistent-no-repository-checkout")

#: Apply to any test module that reads files out of the repository itself --
#: schemas, scripts, ARCHITECTURE.md, the tutorials tree. Distinct from
#: ``skip_without_monorepo``: that one asks for the *cardiacFoam* tree, this
#: one only asks that we are running inside a checkout at all.
skip_without_repo = pytest.mark.skipif(
    repo_root is None,
    reason=(
        "Requires a repository checkout (this module reads files from it). "
        "Not available when running against an installed distribution."
    ),
)

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
