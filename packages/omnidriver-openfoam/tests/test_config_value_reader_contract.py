"""The ConfigValueCapability reader contract (review finding B1).

``tutorial_records.split_unchanged`` / ``record_execution._resolve_and_split``
call the reader with a KEY-PATH TUPLE (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §4
step 7), but the real reader this adapter used to hand back,
``mutators.read_foam_entry(file_path, key, *, scope=None)``, takes a plain
leaf key plus a separate ``scope``. Before this fix,
``OpenFOAMEnvironmentPlugin.get_config_value_reader()`` returned
``read_foam_entry`` unwrapped, so a caller passing a tuple got a scope
argument's worth of nonsense (a ``key`` that was never a single string).

This module proves the adapter now splits a key-path tuple into
``scope``/``key`` itself, against a REAL native file -- not an invented
fixture (CLAUDE.md's "testing against real meshes": real case or native-
source drift gate, nothing invented). The native tutorials root comes ONLY
from ``OMNIDRIVER_NATIVE_TUTORIALS`` (supplied, not discovered); when unset,
this FAILS rather than skipping, so a run that meant to exercise it cannot
silently pass by omission.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

pytestmark = pytest.mark.native


def _native_tutorials_root() -> Path:
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


def test_config_value_reader_splits_a_key_path_tuple_into_scope_and_key():
    root = _native_tutorials_root()
    electro_properties = (
        root / "manufacturedSolutions" / "bathBidomain" / "constant" / "electroProperties"
    )
    assert electro_properties.is_file(), f"fixture path missing: {electro_properties}"

    reader = OpenFOAMEnvironmentPlugin().get_config_value_reader()

    # Core's own contract: a key path is always a TUPLE of segments, never a
    # dotted string -- the reader itself splits the leaf key from its scope.
    value = reader(electro_properties, ("bidomainSolverCoeffs", "conductivitySource"))
    assert value == "uniform"

    # A top-level (unscoped) key is a one-element tuple, not a bare string.
    top_level = reader(electro_properties, ("myocardiumSolver",))
    assert top_level == "bidomainSolver"
