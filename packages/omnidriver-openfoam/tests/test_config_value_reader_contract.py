"""The ``ConfigValueCapability`` reader contract: callers pass a key-path tuple; the adapter splits it into
``scope``/``key`` for ``mutators.read_foam_entry``. Proven on bathBidomain's ``constant/electroProperties``,
committed verbatim as a fixture."""
from __future__ import annotations

from pathlib import Path

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

ELECTRO_PROPERTIES = Path(__file__).resolve().parent / "core" / "fixtures" / "electroProperties.bathBidomain"


def test_config_value_reader_splits_a_key_path_tuple_into_scope_and_key():
    reader = OpenFOAMEnvironmentPlugin().get_config_value_reader()

    # A key path is always a TUPLE of segments, never a dotted string: the reader splits the leaf key from its scope.
    assert reader(ELECTRO_PROPERTIES, ("bidomainSolverCoeffs", "conductivitySource")) == "uniform"
    # A top-level (unscoped) key is a one-element tuple, not a bare string.
    assert reader(ELECTRO_PROPERTIES, ("myocardiumSolver",)) == "bidomainSolver"
