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


class TestCardiacDetection(unittest.TestCase):
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
