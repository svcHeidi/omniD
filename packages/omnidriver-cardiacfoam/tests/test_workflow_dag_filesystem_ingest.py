"""cardiacFoam's electroProperties-variant case marker is discoverable.

Moved from omnidriver/tests/core/test_workflow_dag_filesystem_ingest.py
(Phase 2 Task M2): this test writes only a variant-suffixed
``constant/electroProperties.monodomain`` file (no bare ``electroProperties``)
and checks that cardiacFoam's own ``has_case_marker``/discovery still
recognizes the folder as a runnable case folder -- cardiacFoam vocabulary,
not core's Allrun-driven DAG synthesis rule (which stayed in core, see
``test_workflow_dag_filesystem_ingest.py`` there).
"""
from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from omnidriver.core.runtime.registry import resolve_entry
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(
    CardiacFoamPlugin(),
    source="test:workflow_dag_filesystem_ingest",
)


class TestVariantElectroPropertiesCase(unittest.TestCase):
    def test_variant_electro_properties_case_is_discoverable_and_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tutorials_root = Path(temp_dir)
            case_root = tutorials_root / "variantCase"
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
                overrides={"tutorials_root": tutorials_root},
                driver_context=_CTX,)

            self.assertEqual(resolution["resolution"], "case_folder")
            self.assertTrue(resolution["is_runnable"])


if __name__ == "__main__":
    unittest.main()
