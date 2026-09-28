"""Required case files the cardiac plugin declares."""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:case_file_contract")


def test_cardiac_required_files_include_its_dictionaries() -> None:
    contract = _CTX.capabilities.case_files
    required = contract.required_files()
    assert "constant/electroProperties" in required
    assert "constant/physicsProperties" in required
    assert "system/controlDict" in required
