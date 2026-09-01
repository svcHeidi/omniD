"""Required case files come from the plugin profile, not a core constant."""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def test_generic_plugin_requires_no_solver_dictionaries() -> None:
    contract = generic_openfoam_context().capabilities.case_files
    required = contract.required_files()
    assert "constant/electroProperties" not in required
    assert "constant/physicsProperties" not in required


def test_conditional_files_are_separated_from_required() -> None:
    """Exercises `_CaseFileContractAdapter`'s always/conditional split -- core
    mechanics, not cardiac vocabulary. `MinimalOpenFOAMPlugin(entrypoint=...)`
    is the smallest available fixture that declares a `required="conditional"`
    case-file rule, so the string here is "Allrun" (what that fixture
    declares) rather than the cardiac plugin's "blockMeshDict"; the mechanic
    under test -- conditional files excluded from required_files() -- is the
    same either way."""
    contract = driver_context(
        MinimalOpenFOAMPlugin(entrypoint="Allrun"), source="test"
    ).capabilities.case_files
    assert "Allrun" in contract.conditional_files()
    assert "Allrun" not in contract.required_files()
