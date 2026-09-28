"""The override writers' output bytes, pinned by content digest, and the pure `resolve_entry_overrides`:
it resolves the same document/key the writers write, refuses a shape mismatch at `ParameterAssignment`
construction, and touches no file, checked against a directory snapshot."""

from __future__ import annotations

import hashlib
import math
import os
import stat
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.overrides import (
    apply_electro_property_overrides,
    apply_physics_property_overrides,
    resolve_entry_overrides,
)

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver singleCellSolver;",
        "",
        "singleCellSolverCoeffs",
        "{",
        "    ionicModel BuenoOrovio;",
        "    tissue myocyte;",
        "    singleCellStimulus",
        "    {",
        "        stim_amplitude 0.4;",
        "        stim_period_S1 1000;",
        "    }",
        "}",
        "",
    ]
)

_PHYSICS_TEXT = "type electroModel;\n"

# Mixes both calling conventions, a literal <solver>Coeffs block name and the
# $ELECTRO_MODEL_COEFFS scope token, and includes a scoped two-deep nested key.
_CASE_OVERRIDES = {
    "singleCellSolverCoeffs.tissue": "epicardialCells",
    "singleCellSolverCoeffs.ionicModel": "Gaur",
    "singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": 0.8,
}
_TOKEN_OVERRIDES = {
    "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1": 1200,
}
_PHYSICS_OVERRIDES = {"type": "electroMechanicalModel"}

# The exact bytes the override writers produce for the inputs above.
_ELECTRO_DIGEST_BEFORE = "fe7338046ef82b36772500cdd0e7921235aa851d35044870d240158275a960ed"
_PHYSICS_DIGEST_BEFORE = "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestCharacterizeExistingOverrideBytes(unittest.TestCase):
    def test_apply_electro_property_overrides_bytes_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)

            apply_electro_property_overrides(path, _CASE_OVERRIDES)
            apply_electro_property_overrides(path, _TOKEN_OVERRIDES)

            self.assertEqual(_digest(path), _ELECTRO_DIGEST_BEFORE)
            self.assertEqual(_mode(path), 0o644)

    def test_apply_physics_property_overrides_bytes_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "physicsProperties"
            path.write_text(_PHYSICS_TEXT)

            apply_physics_property_overrides(path, _PHYSICS_OVERRIDES)

            self.assertEqual(_digest(path), _PHYSICS_DIGEST_BEFORE)
            self.assertEqual(_mode(path), 0o644)


def _dir_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """Relative path -> (content digest, mode)."""
    snapshot = {}
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            snapshot[str(entry.relative_to(root))] = (_digest(entry), _mode(entry))
    return snapshot


class TestResolveEntryOverrides(unittest.TestCase):
    def test_resolves_the_same_document_and_key_the_old_path_wrote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)

            before = _dir_snapshot(Path(temp_dir))
            assignments = resolve_entry_overrides(
                path, _CASE_OVERRIDES, document="constant/electroProperties",
                electro_properties_path=path,
            )
            after = _dir_snapshot(Path(temp_dir))

            self.assertEqual(before, after, "resolve_entry_overrides touched a file")

            by_qualified_id = {a.qualified_id: a for a in assignments}
            tissue = by_qualified_id["singleCellSolverCoeffs.tissue"]
            self.assertEqual(tissue.document, "constant/electroProperties")
            self.assertEqual(
                tissue.expanded_key_path(), ("singleCellSolverCoeffs", "tissue"),
            )
            self.assertEqual(tissue.value, "epicardialCells")
            self.assertEqual(tissue.value_kind, "enum")
            self.assertEqual(tissue.source, "case")

            amplitude = by_qualified_id[
                "singleCellSolverCoeffs.singleCellStimulus.stim_amplitude"
            ]
            self.assertEqual(
                amplitude.expanded_key_path(),
                ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude"),
            )
            self.assertEqual(amplitude.value_kind, "scalar")

    def test_resolves_the_token_form_scoped_nested_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)

            assignments = resolve_entry_overrides(
                path, _TOKEN_OVERRIDES, document="constant/electroProperties",
                electro_properties_path=path,
            )

            self.assertEqual(len(assignments), 1)
            assignment = assignments[0]
            self.assertEqual(
                assignment.expanded_key_path(),
                ("singleCellSolverCoeffs", "singleCellStimulus", "stim_period_S1"),
            )
            self.assertEqual(assignment.value_kind, "scalar")
            self.assertEqual(assignment.value, 1200)

    def test_resolves_physics_property_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "physicsProperties"
            path.write_text(_PHYSICS_TEXT)

            assignments = resolve_entry_overrides(
                path, _PHYSICS_OVERRIDES, document="constant/physicsProperties",
            )

            self.assertEqual(len(assignments), 1)
            assignment = assignments[0]
            self.assertEqual(assignment.qualified_id, "type")
            self.assertEqual(assignment.document, "constant/physicsProperties")
            self.assertEqual(assignment.value_kind, "enum")

    def test_nan_for_a_scalar_raises_at_construction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)

            with self.assertRaises(ValueError) as raised:
                resolve_entry_overrides(
                    path,
                    {"singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": math.nan},
                    document="constant/electroProperties",
                    electro_properties_path=path,
                )
            self.assertIn("does not fit", str(raised.exception))

    def test_no_file_is_touched_even_when_it_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)
            before = _dir_snapshot(Path(temp_dir))

            with self.assertRaises(ValueError):
                resolve_entry_overrides(
                    path,
                    {"singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": math.nan},
                    document="constant/electroProperties",
                    electro_properties_path=path,
                )

            self.assertEqual(before, _dir_snapshot(Path(temp_dir)))

    def test_an_undeclared_key_is_refused_not_silently_written(self) -> None:
        """No native utility reads `manufacturedBidomain.fdaBathVariant` under `<solver>Coeffs`."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(_ELECTRO_TEXT)

            with self.assertRaises(ValueError) as raised:
                resolve_entry_overrides(
                    path,
                    {"singleCellSolverCoeffs.manufacturedBidomain.fdaBathVariant": "electrodePair"},
                    document="constant/electroProperties",
                    electro_properties_path=path,
                )
            self.assertIn("is not declared", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
