"""Contract tests for the DataArtifact vocabulary."""
from __future__ import annotations

import dataclasses
import typing
import unittest

from omnidriver.core.runtime.models import (
    ArtifactFormat,
    DataArtifact,
)


class TestDataArtifact(unittest.TestCase):
    def test_constructs_with_required_fields_only(self) -> None:
        artifact = DataArtifact(
            artifact_id="vm_probe",
            path_pattern="postProcessing/probes/{instance}/Vm",
            format="csv_probe",
        )
        self.assertEqual(artifact.artifact_id, "vm_probe")
        self.assertEqual(artifact.path_pattern, "postProcessing/probes/{instance}/Vm")
        self.assertEqual(artifact.format, "csv_probe")

    def test_defaults_are_safe_for_predictor_merging(self) -> None:
        """Defaults must let predict_data_artifacts merge static + derived artifacts without None-vs-tuple ambiguity (plan section 2.1)."""
        artifact = DataArtifact(
            artifact_id="x",
            path_pattern="foo",
            format="openfoam_log",
        )
        self.assertEqual(artifact.variables, ())  # never None
        self.assertEqual(artifact.description, "")
        self.assertEqual(artifact.produced_by, "")
        self.assertIs(artifact.optional, False)
        self.assertIs(artifact.instance_indexed, False)

    def test_is_frozen(self) -> None:
        """Artifacts are value objects embedded in agent manifests; mutation would silently desync the manifest from later reads."""
        artifact = DataArtifact(
            artifact_id="x",
            path_pattern="foo",
            format="openfoam_log",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            artifact.artifact_id = "y"  # type: ignore[misc]

    def test_construction_rejects_unknown_placeholder(self) -> None:
        """A typo (e.g. {caseId}) in path_pattern must fail at construction, not silently propagate where it can only be detected when an agent tries to expand it later."""
        with self.assertRaises(ValueError) as ctx:
            DataArtifact(
                artifact_id="typo",
                path_pattern="postProcessing/{caseId}.txt",
                format="csv_probe",
            )
        self.assertIn("caseId", str(ctx.exception))

    def test_construction_with_known_placeholders_succeeds(self) -> None:
        DataArtifact(
            artifact_id="ok",
            path_pattern="results/{case_id}/{instance}/Vm",
            format="openfoam_time_dirs",
        )

    def test_construction_with_no_placeholders_succeeds(self) -> None:
        DataArtifact(
            artifact_id="static",
            path_pattern="postProcessing/exact_error.json",
            format="json_summary",
        )

    def test_accepts_variables_tuple(self) -> None:
        artifact = DataArtifact(
            artifact_id="ionic",
            path_pattern="postProcessing/cellModel.dat",
            format="csv_sweep",
            variables=("Vm", "Iion", "Cai"),
        )
        self.assertEqual(artifact.variables, ("Vm", "Iion", "Cai"))


class TestArtifactFormatIsOpen(unittest.TestCase):
    """ArtifactFormat is deliberately NOT a closed Literal: most format strings in practice are a solver plugin's own vocabulary for its own outputs, which core has no business validating."""

    def test_artifact_format_is_a_plain_string_type(self) -> None:
        self.assertIs(ArtifactFormat, str)
        self.assertEqual(typing.get_args(ArtifactFormat), ())

    def test_a_plugin_owned_format_string_is_accepted_without_validation(self) -> None:
        """DataArtifact does not validate .format at all -- a plugin is free to use vocabulary core has never heard of (e.g. a FEniCS plugin's "xdmf_sequence")."""
        artifact = DataArtifact(
            artifact_id="a", path_pattern="p", format="xdmf_sequence",
        )
        self.assertEqual(artifact.format, "xdmf_sequence")


if __name__ == "__main__":
    unittest.main()
