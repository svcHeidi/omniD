"""cardiacFoam's own capability hooks, not a core fallback, decide case compatibility.

The generic counterpart, ``TestGenericPluginDoesNotInheritCardiacSemantics``, stays in core.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseCompatibilityRequest
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def _cardiac_looking_case() -> Path:
    """A case carrying every marker the cardiac fallbacks look for."""
    case_root = Path(tempfile.mkdtemp())
    constant = case_root / "constant"
    system = case_root / "system"
    constant.mkdir()
    system.mkdir()
    (constant / "electroProperties").write_text(
        "myocardiumSolver singleCellSolver;\n"
        "singleCellSolverCoeffs\n{\n    ionicModel TNNP;\n}\n"
    )
    (constant / "physicsProperties").write_text("physics electrophysiology;\n")
    for name in ("controlDict", "fvSchemes", "fvSolution"):
        (system / name).write_text("// placeholder\n")
    return case_root


class TestCardiacPluginBehaviourIsUnchanged(unittest.TestCase):
    """Gating must be invisible to cardiacFoam, which implements every hook."""

    def _cardiac_capabilities(self):
        from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

        context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:cardiacfoam")
        return context.capabilities

    def test_cardiac_plugin_still_claims_a_cardiac_case(self) -> None:
        capabilities = self._cardiac_capabilities()
        request = CaseCompatibilityRequest(case_root=_cardiac_looking_case())

        self.assertTrue(capabilities.case_compatibility.has_case_marker(request))

    def test_cardiac_plugin_still_declares_it_runnable(self) -> None:
        capabilities = self._cardiac_capabilities()
        request = CaseCompatibilityRequest(case_root=_cardiac_looking_case())

        self.assertTrue(
            capabilities.case_compatibility.is_runnable_without_workflow(request)
        )


if __name__ == "__main__":
    unittest.main()
