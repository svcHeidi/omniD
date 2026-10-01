import os
import pytest
from pathlib import Path

os.environ["SKIP_ENV_DIAGNOSTICS"] = "1"


@pytest.fixture(autouse=True)
def _toy_plugins_are_importable(monkeypatch):
    """A child process resolves ``--plugin plugins.<module>:<Class>`` through PYTHONPATH."""
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        p for p in (str(Path(__file__).resolve().parent), os.environ.get("PYTHONPATH", "")) if p
    ))


from omnidriver.core.specs.paths import repo_root_default


def _repo_root_or_none() -> Path | None:
    """The repository root, or ``None`` outside a checkout (e.g. an installed wheel)."""
    # A module that calls repo_root_default() at import time would turn "no
    # checkout" into an uncatchable collection error; see check-wheel-artifact.py.
    try:
        return repo_root_default()
    except RuntimeError:
        return None


#: The repository root, resolved once at collection time; ``None`` outside a checkout.
repo_root: Path | None = _repo_root_or_none()

#: Placeholder so a module-level ``REPO_ROOT / ...`` expression still constructs
#: without a checkout; never read, since ``skip_without_repo`` skips first.
NO_REPO_ROOT = Path("/nonexistent-no-repository-checkout")

#: Apply to any test module that reads files out of the repository itself --
#: schemas, scripts, ARCHITECTURE.md, the tutorials tree. Distinct from
#: ``skip_without_monorepo``, which asks for the cardiacFoam tree specifically.
skip_without_repo = pytest.mark.skipif(
    repo_root is None,
    reason=(
        "Requires a repository checkout (this module reads files from it). "
        "Not available when running against an installed distribution."
    ),
)

def _cardiacfoam_monorepo_root() -> Path | None:
    """The cardiacFoam monorepo root, if this checkout sits inside one."""
    # Local copy, not an import of omnidriver-cardiacfoam: core tests must
    # not import cardiac vocabulary (scripts/check-import-boundaries.py).
    for parent in Path(__file__).resolve().parents:
        if (parent / "tutorials").exists() and (parent / "applications").exists():
            return parent
    return None


#: The monorepo root resolved once at collection time.  ``None`` in standalone.
monorepo_root: Path | None = _cardiacfoam_monorepo_root()

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
    """Whether ``default_driver_context()`` resolves to a single clean answer."""
    from omnidriver.core.plugin_interface import default_driver_context

    try:
        default_driver_context()
    # LookupError: _default_selection's "no adapter" / "every name contested"
    # cases. ValueError: provider_stack.compose's packaging conflicts (see
    # above). These are the only two exception types either path can raise.
    except (LookupError, ValueError):
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
    """A :class:`DriverContext` per discoverable plugin, skipping when none is installed."""
    from omnidriver.core import plugin_discovery

    discovered = plugin_discovery.discover_plugins()
    if not discovered:
        pytest.skip("no omnidriver.plugins entry points installed")
    # discover_plugins() values are EntryPoint objects, not plugin classes;
    # load_discovered_plugin() loads the class and builds the context.
    return [
        plugin_discovery.load_discovered_plugin(name)
        for name in discovered
    ]
