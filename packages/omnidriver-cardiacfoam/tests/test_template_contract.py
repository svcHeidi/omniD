from __future__ import annotations

import unittest
from pathlib import Path

from omnidriver.dict_entries import all_documented_driver_paths
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default left
# to discover. The documented driver paths compared here are cardiacFoam's.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:template_contract")


def _template_path() -> Path:
    import omnidriver.cardiacfoam

    return (
        Path(omnidriver.cardiacfoam.__file__).parent
        / "fixtures" / "template" / "constant" / "electroProperties"
    )


def _read(path: Path) -> str:
    return path.read_text()


class TestTemplateAndSchemaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template_path = _template_path()

    def test_template_uses_code_backed_selector_keys(self) -> None:
        template = _read(self.template_path)

        self.assertIn("myocardiumSolver", template)
        self.assertIn("monodomainSolverCoeffs", template)
        self.assertIn("singleCellSolverCoeffs", template)
        self.assertIn("ecgSolver", template)
        self.assertIn("electrodePositions", template)
        self.assertIn("conductivityIntracellular", template)
        self.assertIn("conductivityExtracellular", template)
        self.assertIn("monodomain1DSolver", template)
        self.assertIn("phiERefPoint", template)
        self.assertIn("purkinjeGraphModelCoeffs", template)

        # Bath-coupled ECG support keys (canonical C++ key set).
        self.assertIn("bathPotentialDomain", template)
        self.assertIn("extracellularPotentialDomain", template)
        self.assertIn("bathCellZones", template)
        self.assertIn("bathConductivityField", template)
        self.assertIn("torsoECG", template)
        self.assertIn("groundPatches", template)
        self.assertIn("surfaceCurrentPatches", template)

        self.assertNotIn("ecgDomainModel", template)
        self.assertNotIn("pseudoECGElectroCoeffs", template)
        self.assertNotIn("monoDomainElectroCoeffs", template)
        self.assertNotIn("phiEReferenceCell", template)
        self.assertNotIn("purkinjeNetworkModelCoeffs", template)
        self.assertNotIn("bidomainBathECG", template)

    def test_driver_schema_paths_follow_template_truth_family(self) -> None:
        documented = set(all_documented_driver_paths(_CTX))

        expected = {
            "myocardiumSolver",
            "$ELECTRO_MODEL_COEFFS.solutionAlgorithm",
            "$ELECTRO_MODEL_COEFFS.verificationModel.type",
            "$ELECTRO_MODEL_COEFFS.bathPotentialDomain.bathCellZones",
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver",
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.electrodePositions.<electrode>",
            "$ELECTRO_MODEL_COEFFS.conductivityIntracellular",
            "$ELECTRO_MODEL_COEFFS.conductivityExtracellular",
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.conductionSystemDomain",
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.graphFile",
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.electroDomainCoupler",
            "$ELECTRO_MODEL_COEFFS.phiERefPoint",
        }
        self.assertTrue(expected.issubset(documented))

        forbidden_fragments = (
            "ecgDomainModel",
            "pseudoECGElectroCoeffs",
            ".electrodes.",
            "monoDomainElectroCoeffs",
            "singleCellElectroCoeffs",
            "phiEReferenceCell",
            "purkinjeNetworkModelCoeffs",
            ".pvjNodes",
            ".pvjLocations",
            "bidomainBath",
        )
        self.assertFalse(
            [path for path in documented if any(fragment in path for fragment in forbidden_fragments)]
        )


if __name__ == "__main__":
    unittest.main()
