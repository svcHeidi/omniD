"""A whole-repo run must be able to import every package's test helpers.

Each package's own ``pyproject.toml`` sets ``pythonpath = ["tests"]``, so
``pytest packages/<pkg>/tests`` -- what every CI job runs -- can import a
helper module sitting at that package's tests root. A whole-repo run
(``pytest packages/``) resolves its config from the *workspace*
``pyproject.toml`` instead, and only the roots listed there are importable.
``addopts = --import-mode=importlib`` means there is no basedir fallback to
paper over the difference.

So a package missing from the workspace list is invisible until someone runs
the whole repo at once, and then it fails as a bare ``ModuleNotFoundError``
during collection -- which aborts the run before any other test reports.

That happened on 2026-09-18: core/adapter-boundaries relocated the
OpenFOAM-dependent core tests into ``packages/omnidriver-openfoam/tests/core/``
next to a new ``openfoam_assertions`` helper. Every per-package job stayed
green and the branch looked clean; the combined run could not collect two of
the relocated modules.

This guard is deliberately about the *workspace* file only. It says nothing
about which helpers exist -- just that if a package has tests, a combined run
can reach that package's tests root the same way a per-package run can.
"""
from __future__ import annotations

import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - the project floor is 3.11
    import tomli as tomllib

from conftest import NO_REPO_ROOT, repo_root, skip_without_repo

_ROOT = repo_root if repo_root is not None else NO_REPO_ROOT


@skip_without_repo
def test_every_package_with_tests_is_on_the_workspace_pythonpath() -> None:
    workspace = _ROOT / "pyproject.toml"
    assert workspace.is_file(), (
        f"expected the workspace pyproject at {workspace}; fix the path rather "
        "than letting this guard pass by finding nothing."
    )

    config = tomllib.loads(workspace.read_text())
    listed = set(
        config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get(
            "pythonpath", []
        )
    )

    packages_dir = _ROOT / "packages"
    assert packages_dir.is_dir(), f"no packages/ directory at {packages_dir}"

    expected = {
        f"packages/{package.name}/tests"
        for package in sorted(packages_dir.iterdir())
        if (package / "tests").is_dir()
    }

    # A guard that found no packages would pass while checking nothing.
    assert len(expected) >= 3, (
        f"expected several packages with tests under {packages_dir}, found "
        f"{sorted(expected)} -- this guard is not looking where it thinks"
    )

    missing = sorted(expected - listed)
    assert missing == [], (
        "these packages have a tests/ directory that a whole-repo run cannot "
        "import helpers from, because the workspace pyproject's "
        "[tool.pytest.ini_options] pythonpath does not list it:\n  "
        + "\n  ".join(missing)
        + "\n\nA per-package run will still pass, because each package sets its "
        "own pythonpath = [\"tests\"]. Add the entry to the workspace list."
    )
