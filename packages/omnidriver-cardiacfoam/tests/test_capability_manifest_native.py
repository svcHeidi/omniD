"""The capability manifest reaches describe/strict_plan for a real tutorial.

Uses the ``singleCell`` record; the manifest is built from the plugin identity, so any entry proves it.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

pytestmark = pytest.mark.native

_SINGLE_CELL_RELPATH = "electrophysiologyProtocols/singleCell"

_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:capability_manifest_native",
)


def _native_tutorials_root() -> Path:
    """Copied, not imported: each native module is collected with no import-time dependency on a sibling."""
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _stage_single_cell(cases_root: Path) -> None:
    """Copy only ``constant/`` and ``system/`` of the native singleCell case: all this record reads."""
    native_case = _native_tutorials_root() / _SINGLE_CELL_RELPATH
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")
    scratch_case = cases_root / _SINGLE_CELL_RELPATH
    scratch_case.mkdir(parents=True, exist_ok=True)
    for name in ("constant", "system"):
        src = native_case / name
        if src.is_dir():
            shutil.copytree(src, scratch_case / name)


def test_describe_entry_includes_capability_manifest(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_single_cell(cases_root)
    payload = describe_entry(
        "singleCell", overrides={"cases_root": str(cases_root)}, driver_context=_CTX,
    )
    manifest = payload["capability_manifest"]
    assert "cardiacFoam" in manifest["allowed_commands"]["plugin"]
    assert "electro" in manifest["samplable_fields"]


def test_strict_plan_carries_capability_manifest(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_single_cell(cases_root)
    report = strict_plan(
        "singleCell", overrides={"cases_root": str(cases_root)}, driver_context=_CTX,
        scratch_root=str(tmp_path / "scratch"),
    ).to_json()
    assert "cardiacFoam" in report["capability_manifest"]["allowed_commands"]["plugin"]
