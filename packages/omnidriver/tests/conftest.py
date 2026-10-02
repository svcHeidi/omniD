import os
import pytest
from pathlib import Path


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

#: Apply to any test module that reads files out of the omnidriver repository
#: itself -- schemas, scripts, ARCHITECTURE.md.
skip_without_repo = pytest.mark.skipif(
    repo_root is None,
    reason=(
        "Requires a repository checkout (this module reads files from it). "
        "Not available when running against an installed distribution."
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
