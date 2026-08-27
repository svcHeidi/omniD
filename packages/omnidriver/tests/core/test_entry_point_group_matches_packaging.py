"""The group constant and the packaging metadata must name the same group.

They did not, from the monorepo rename until this test existed: packaging moved
to 'omnidriver.plugins' and plugin_discovery.py kept reading 'driverfoam.plugins',
so --plugin <name> resolved nothing in any install. Every other discovery test
monkeypatches the _entry_points() seam and therefore cannot catch this.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from omnidriver.core.plugin_discovery import ENTRY_POINT_GROUP

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _declared_plugin_groups() -> dict[str, list[str]]:
    """Map each packages/*/pyproject.toml to the entry-point groups it declares
    that look like a plugin group (contain '.plugins')."""
    found: dict[str, list[str]] = {}
    for pyproject in sorted((_REPO_ROOT / "packages").glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text())
        groups = data.get("project", {}).get("entry-points", {})
        plugin_groups = [name for name in groups if ".plugins" in name]
        if plugin_groups:
            found[pyproject.parent.name] = sorted(plugin_groups)
    return found


def test_every_package_registers_into_the_group_core_reads() -> None:
    declared = _declared_plugin_groups()
    assert declared, "no packages/*/pyproject.toml declares a *.plugins group"
    offenders = {
        package: groups
        for package, groups in declared.items()
        if groups != [ENTRY_POINT_GROUP]
    }
    assert offenders == {}, (
        f"plugin_discovery.ENTRY_POINT_GROUP is {ENTRY_POINT_GROUP!r} but these "
        f"packages register elsewhere: {offenders}. A plugin registered into a "
        "group core does not read is undiscoverable."
    )
