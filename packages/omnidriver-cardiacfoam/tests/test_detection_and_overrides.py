#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_detection_and_overrides
#
# Description
#     Tests the cardiacFoam plugin's electroProperties detection helpers and
#     the electro/physics-property override appliers on top of them, including
#     the plugin-local `$ELECTRO_MODEL_COEFFS` scope token.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.detection import (
    detect_electro_coeffs_scope,
    detect_ionic_export_list,
    detect_ionic_model_name,
)
from omnidriver.cardiacfoam.overrides import (
    apply_electro_property_overrides,
    apply_physics_property_overrides,
    normalize_entry_overrides,
)
from cardiacfoam_assertions import assert_foam_entry


class TestCardiacPropertyOverrides(unittest.TestCase):
    def test_single_cell_stimulus_updates_use_nested_scope(self) -> None:
        text = "\n".join(
            [
                "singleCellSolverCoeffs",
                "{",
                "    singleCellStimulus",
                "    {",
                "        stim_amplitude 0.4;",
                "        stim_period_S1 1000;",
                "        stim_period_S2 250;",
                "        nstim1 10;",
                "        nstim2 2;",
                "    }",
                "}",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(text)

            apply_electro_property_overrides(
                path,
                {
                    "singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": 0.8,
                    "singleCellSolverCoeffs.singleCellStimulus.stim_period_S1": 1200,
                    "singleCellSolverCoeffs.singleCellStimulus.stim_period_S2": 300,
                    "singleCellSolverCoeffs.singleCellStimulus.nstim1": 12,
                    "singleCellSolverCoeffs.singleCellStimulus.nstim2": 3,
                },
            )

            stimulus = ("singleCellSolverCoeffs", "singleCellStimulus")
            for key, expected in (
                ("stim_amplitude", "0.8"),
                ("stim_period_S1", "1200"),
                ("stim_period_S2", "300"),
                ("nstim1", "12"),
                ("nstim2", "3"),
            ):
                assert_foam_entry(path, key, expected, scope=stimulus)

    def test_detect_electro_coeffs_scope(self) -> None:
        text = "\n".join(
            [
                "myocardiumSolver monodomainSolver;",
                "",
                "monodomainSolverCoeffs",
                "{",
                "    ionicModel TNNP;",
                "}",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(text)
            self.assertEqual(detect_electro_coeffs_scope(path), "monodomainSolverCoeffs")

    def test_normalize_entry_overrides_supports_electro_scope_token(self) -> None:
        text = "\n".join(
            [
                "myocardiumSolver singleCellSolver;",
                "",
                "singleCellSolverCoeffs",
                "{",
                "    ionicModel BuenoOrovio;",
                "}",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(text)

            normalized = normalize_entry_overrides(
                {"$ELECTRO_MODEL_COEFFS.ionicModel": "Gaur"},
                electro_properties_path=path,
            )

            self.assertEqual(
                normalized,
                [{"key": "ionicModel", "value": "Gaur", "scope": ("singleCellSolverCoeffs",)}],
            )

    def test_apply_electro_property_overrides_handles_nested_paths(self) -> None:
        text = "\n".join(
            [
                "myocardiumSolver singleCellSolver;",
                "",
                "singleCellSolverCoeffs",
                "{",
                "    ionicModel BuenoOrovio;",
                "    singleCellStimulus",
                "    {",
                "        stim_period_S1 1000;",
                "    }",
                "}",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "electroProperties"
            path.write_text(text)

            apply_electro_property_overrides(
                path,
                {
                    "$ELECTRO_MODEL_COEFFS.ionicModel": "Gaur",
                    "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1": 750,
                },
            )

            assert_foam_entry(
                path, "ionicModel", "Gaur", scope="singleCellSolverCoeffs"
            )
            assert_foam_entry(
                path,
                "stim_period_S1",
                "750",
                scope=("singleCellSolverCoeffs", "singleCellStimulus"),
            )

    def test_apply_physics_property_overrides_updates_root_dictionary(self) -> None:
        text = "\n".join(
            [
                "type electroModel;",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "physicsProperties"
            path.write_text(text)

            apply_physics_property_overrides(path, {"type": "electroMechanicalModel"})
            assert_foam_entry(path, "type", "electroMechanicalModel")


_QUOTED_BRACE_ELECTRO_PROPERTIES = (
    "FoamFile{ version 2.0; format ascii; class dictionary; object electroProperties; }\n"
    'myocardiumSolver monodomainSolver;\n'
    "monodomainSolverCoeffs\n{\n"
    '    note  "a value with { an unbalanced brace";\n'
    "    ionicModel TenTusscherPanfilov;\n"
    "    activeTensionModel simple;\n"
    "    verificationModel\n    {\n        type manufactured;\n    }\n"
    "    ionic\n    {\n        export (Vm Cai);\n    }\n"
    "}\n"
)


def test_detect_ionic_model_name_survives_a_quoted_brace_inside_the_active_scope():
    """The quoted brace sits inside the active Coeffs block, where brace depth is counted."""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "electroProperties"
        path.write_text(_QUOTED_BRACE_ELECTRO_PROPERTIES)
        assert detect_ionic_model_name(path) == "TenTusscherPanfilov"


_BLOCK_COMMENT_ELECTRO_PROPERTIES = (
    "FoamFile{ version 2.0; format ascii; class dictionary; object electroProperties; }\n"
    "myocardiumSolver monodomainSolver;\n"
    "monodomainSolverCoeffs\n{\n"
    "    /* TODO: fix the { syntax someday */\n"
    "    ionicModel TenTusscherPanfilov;\n"
    "}\n"
)


def test_detect_ionic_model_name_survives_a_block_comment_inside_the_active_scope():
    """A `{` inside a `/* */` block comment in the active Coeffs block must not count as depth."""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "electroProperties"
        path.write_text(_BLOCK_COMMENT_ELECTRO_PROPERTIES)
        assert detect_ionic_model_name(path) == "TenTusscherPanfilov"


_NESTED_SUBBLOCK_BEFORE_EXPORT = (
    "FoamFile{ version 2.0; format ascii; class dictionary; object electroProperties; }\n"
    "myocardiumSolver monodomainSolver;\n"
    "monodomainSolverCoeffs\n{\n"
    "    ionicModel TenTusscherPanfilov;\n"
    "    outputVariables\n    {\n"
    "        ionic\n        {\n"
    "            options\n            {\n                someKnob 1;\n            }\n"
    "            export (Vm Cai);\n"
    "        }\n"
    "    }\n"
    "}\n"
)


def test_detect_ionic_export_list_survives_a_nested_subblock_before_export():
    """A nested sub-block before export(...) must not hide the list (None reads as "not declared")."""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "electroProperties"
        path.write_text(_NESTED_SUBBLOCK_BEFORE_EXPORT)
        assert detect_ionic_export_list(path) == ("Vm", "Cai")


if __name__ == "__main__":
    unittest.main()
