"""cardiacFoam's electroProperties-variant case marker is discoverable: a case
with only ``constant/electroProperties.monodomain`` is a runnable case folder.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from omnidriver.core.runtime.registry import resolve_entry
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(),
    source="test:workflow_dag_filesystem_ingest",
)


class TestVariantElectroPropertiesCase(unittest.TestCase):
    def test_variant_electro_properties_case_is_discoverable_and_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases_root = Path(temp_dir)
            case_root = cases_root / "variantCase"
            (case_root / "constant").mkdir(parents=True, exist_ok=True)
            (case_root / "system").mkdir(parents=True, exist_ok=True)
            (case_root / "constant" / "electroProperties.monodomain").write_text(
                "myocardiumSolver monodomainSolver;\n"
            )
            (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")
            for relpath in ("controlDict", "fvSchemes", "fvSolution"):
                (case_root / "system" / relpath).write_text("\n")

            resolution = resolve_entry(
                "variantCase",
                overrides={"cases_root": cases_root},
                driver_context=_CTX,)

            self.assertEqual(resolution["resolution"], "case_folder")
            self.assertTrue(resolution["is_runnable"])


if __name__ == "__main__":
    unittest.main()
