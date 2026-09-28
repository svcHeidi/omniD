"""The ``ConfigValueCapability`` reader contract: callers pass a key-path tuple; the adapter splits it into ``scope``/``key`` for ``mutators.read_foam_entry``.

Proven against a real native tutorials tree, never an invented fixture.
``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered; this test
fails rather than skips when it is unset.
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
