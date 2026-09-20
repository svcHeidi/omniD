import os
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
        "Clone the full repository or run with --cases-root to enable this test."
    ),
)


def _default_adapter_resolves() -> bool:
    """Whether exactly one ``omnidriver.plugins`` adapter is installed.

    ``default_driver_context()`` raises ``LookupError`` with zero adapters
    installed (e.g. the ``test-core`` CI job, which installs none) or with
    two or more (e.g. ``test-cardiac``/``test-cardiaccore``, which each
    install two: a solver adapter plus the ``omnidriver-openfoam`` dependency
    it pulls in, which registers its own entry point). Computed once at
    collection time, matching ``repo_root``/``monorepo_root`` above.
    """
    from omnidriver.core.plugin_interface import default_driver_context

    try:
        default_driver_context()
    except LookupError:
        return False
    return True


#: Apply to any test module whose CLI/RunDocument round-trip calls omit
#: ``--plugin`` and rely on ``default_driver_context()``'s implicit
#: resolution -- which only succeeds when exactly one adapter is installed.
#: Distinct from ``skip_without_monorepo``: this is about how many adapter
#: *packages* are installed, not whether a monorepo checkout exists.
skip_without_single_adapter = pytest.mark.skipif(
    not _default_adapter_resolves(),
    reason=(
        "Requires exactly one omnidriver.plugins adapter installed so "
        "default_driver_context() has an unambiguous answer; this test's "
        "CLI calls omit --plugin. See test-openfoam's CI job."
    ),
)


@pytest.fixture
def driver_context_for_installed_plugins() -> list:
    """A :class:`DriverContext` per discoverable plugin, skipping when none is
    installed.

    ``plugin_discovery.discover_plugins()`` keys on entry-point name but its
    values are ``EntryPoint`` objects, not plugin classes -- go through
    ``load_discovered_plugin`` (which loads the class *and* builds the
    context via ``driver_context()``) rather than calling ``entry_point()``
    a second time.
    """
    from omnidriver.core import plugin_discovery

    discovered = plugin_discovery.discover_plugins()
    if not discovered:
        pytest.skip("no omnidriver.plugins entry points installed")
    return [
        plugin_discovery.load_discovered_plugin(name)
        for name in discovered
    ]
