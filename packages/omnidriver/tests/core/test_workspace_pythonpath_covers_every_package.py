"""A whole-repo run must be able to import every package's test helpers."""
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
