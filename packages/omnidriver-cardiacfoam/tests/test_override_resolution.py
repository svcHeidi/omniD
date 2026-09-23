"""Phase 3 Task 2: `apply_entry_overrides` becomes a resolver.

Two things are under test:

1. A **characterization test** of `apply_electro_property_overrides` /
   `apply_physics_property_overrides` as they behave today (content digests,
   not existence -- an existence check passes for five empty files). It must
   pass before Task 2's change and unchanged after, because the transitional
   `apply_entry_overrides` keeps its write behaviour for one release.

2. Tests for the new pure `resolve_entry_overrides`: it must round-trip a
   representative override set (including a scoped nested key) to the same
   document/key the old path wrote, it must refuse a shape mismatch
   (`nan` for a `scalar`) at `ParameterAssignment` construction, and it must
   touch no file at all -- checked against a directory snapshot, not an
   assumption.
"""

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

# The representative override set exercised below. It deliberately mixes both
# calling conventions this codebase's own tutorials and tests use: a literal,
# already-resolved <solver>Coeffs block name (every real tutorial call site --
# e.g. `single_cell.py`'s `electro_properties_scope`) and the plugin-local
# `$ELECTRO_MODEL_COEFFS` scope token (only `test_detection_and_overrides.py`
# and the CLI's `--apply` path use the token form today). A scoped, two-deep
# nested key (`singleCellStimulus.stim_period_S1`) is included, per Task 2
# Step 2's instruction.
_CASE_OVERRIDES = {
    "singleCellSolverCoeffs.tissue": "epicardialCells",
    "singleCellSolverCoeffs.ionicModel": "Gaur",
    "singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": 0.8,
}
_TOKEN_OVERRIDES = {
    "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1": 1200,
}
_PHYSICS_OVERRIDES = {"type": "electroMechanicalModel"}

# Captured 2026-09-23 against HEAD 722c1a4, from the unmodified
# `apply_electro_property_overrides`/`apply_physics_property_overrides` --
# see this task's report for the capture script. This is the "before" bytes
# Task 2 must reproduce exactly through the new resolver + commit path.
_ELECTRO_DIGEST_BEFORE = "fe7338046ef82b36772500cdd0e7921235aa851d35044870d240158275a960ed"
_PHYSICS_DIGEST_BEFORE = "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestCharacterizeExistingOverrideBytes(unittest.TestCase):
    """Pins today's exact output bytes. Must pass before AND after Task 2."""

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
    """Path (relative) -> (content digest, mode). Purity means this is
    identical before and after resolve_entry_overrides runs -- a dry run
    that touches nothing costs nothing to prove wrong."""
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
        """`manufacturedBidomain.fdaBathVariant` (used by the checked-in
        `manufactured_bath_bidomain` tutorial) is exactly this case in
        production -- see this task's report. The catalog's own 2026-09-19
        note records that no native utility reads that key under
        `<solver>Coeffs`; writing it is a silent no-op the OLD unchecked
        `apply_entry_overrides` could not detect and the resolver now can.
        """
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
