"""Content pins for the ``checkMeshGeometry`` utility manifest this package ships."""

from __future__ import annotations

import unittest

from omnidriver.cardiacfoam.command_authorization import utility_manifests

UTILITY_CATALOG = utility_manifests()


class TestCheckMeshGeometryCatalogued(unittest.TestCase):
    def test_present_and_mesh_category(self):
        self.assertIn("checkMeshGeometry", UTILITY_CATALOG)
        entry = UTILITY_CATALOG["checkMeshGeometry"]
        self.assertEqual(entry.category, "mesh")
        self.assertTrue(entry.requires_mesh)

    def test_flags_reflect_detect_only_default(self):
        flag_names = {f.name for f in UTILITY_CATALOG["checkMeshGeometry"].flags}
        self.assertIn("-region", flag_names)
        self.assertIn("-scale", flag_names)
        self.assertIn("-rescale", flag_names)
        # Detect-only is the default, so there is no -noScale flag.
        self.assertNotIn("-noScale", flag_names)

    def test_artifact_id_typo_fixed(self):
        produced = {p.artifact_id for p in UTILITY_CATALOG["checkMeshGeometry"].produces}
        self.assertIn("polymesh_scaled", produced)
        self.assertNotIn("polymes_scaled", produced)
