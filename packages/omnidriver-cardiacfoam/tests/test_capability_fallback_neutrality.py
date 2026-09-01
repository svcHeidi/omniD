"""cardiacFoam's own capability hooks, not a core fallback, decide these.

Moved from core's ``tests/core/test_capability_fallback_neutrality.py``
(Phase 2, Milestone 3): Phase 2 Task 7 deleted the thirteen ``plugin_id ==
"org.cardiacfoam"`` gates once the standing census
(``test_no_cardiac_gate_is_reached.py``) proved none of them was still
reached -- ``CardiacFoamPlugin`` now implements every hook directly, so
``TestCardiacPluginBehaviourIsUnchanged`` no longer exercises any core
dispatch decision; it now asserts only cardiacFoam's own hook
implementations (``has_case_marker`` / ``is_runnable_without_workflow``).
Its generic counterpart, ``TestGenericPluginDoesNotInheritCardiacSemantics``,
stays in core: ``GenericOpenFOAMPlugin`` implements none of the corresponding
hooks, so those four tests still exercise core's now-unconditional (ungated)
fallback refusals.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseCompatibilityRequest
from omnidriver.core.plugin_interface import driver_context


def _cardiac_looking_case() -> Path:
    """A case carrying every marker the cardiac fallbacks look for.

    If a cardiac fallback answers for the generic plugin, this case is
    claimed. If the fallback is correctly gated, it is not.
    """
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

        context = driver_context(CardiacFoamPlugin(), source="test:cardiacfoam")
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
