"""Core carries no cardiac or solver name."""
from __future__ import annotations

import importlib

import pytest

from omnidriver.cli import build_parser

_MOVED_OUT = (
    ("omnidriver.core.contracts.dictionary", "get_heterogeneity_models"),
    ("omnidriver.core.contracts.dictionary", "get_electro_property_entry_groups"),
    ("omnidriver.core.specs.paths", "cardiacfoam_monorepo_root"),
)


@pytest.mark.parametrize(("module", "name"), _MOVED_OUT)
def test_a_cardiac_symbol_is_not_defined_in_core(module, name):
    assert not hasattr(importlib.import_module(module), name), (
        f"{module}.{name} is cardiac vocabulary; it lives in omnidriver-cardiacfoam"
    )


#: Solver and tutorial names the CLI help must not carry.
_SOLVER_WORDS = (
    "OpenFOAM", "openfoam", "cardiac", "singleCell", "niederer", "manufactured",
    "restitutionCurves", "genericCase", "randomCase", "bashrc",
)


def test_cli_help_names_no_solver_or_tutorial():
    help_text = build_parser().format_help()
    assert [word for word in _SOLVER_WORDS if word in help_text] == []
