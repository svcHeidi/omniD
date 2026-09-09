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
#     manufactured_monodomain_pseudo_ecg
#
# Description
#     Defines configuration template for manufactured monodomain with pseudo ECG
#     for FDA verification.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#
from __future__ import annotations

from ..ids import CardiacTutorialID

from pathlib import Path

from .shared import (
    CONTROL_DICT_RELPATH,
    ELECTRO_PROPERTIES_RELPATH as SHARED_ELECTRO_PROPERTIES_RELPATH,
    OUTPUT_DIR_NAME,
    RUN_CASE_SCRIPT_RELPATH,
)


TUTORIAL_NAME = CardiacTutorialID.MANUFACTURED_MONODOMAIN_PSEUDO_ECG.value
CASE_DIR_NAME = "manufacturedSolutions/monodomainPseudoECG"
SETUP_DIR_NAME = "setup"
NUMBER_CELLS = (10, 20, 40, 80)
DT_VALUES = (
    0.00892857,
    0.00224215,
    0.000560538,
    0.000140174,
)
DIMENSIONS = ("1D", "2D", "3D")
SOLVER_TYPES = ("implicit",)
PIECEWISE_SWEEP = True
ELECTRO_PROPERTIES_SCOPE = "monodomainSolverCoeffs"
ELECTRO_PROPERTIES_RELPATH = SHARED_ELECTRO_PROPERTIES_RELPATH
BLOCK_MESH_DICT_TEMPLATE = "system/blockMeshDict.{dimension}"
RUN_SCRIPT_RELPATH = RUN_CASE_SCRIPT_RELPATH
RUN_IN_PARALLEL = True
VERIFICATION_MODEL_TYPE = "manufacturedFDAMonodomainVerifier"
ECG_ENABLED = True
ECG_REFERENCE_QUADRATURE_ORDER = 96
ECG_CHECK_QUADRATURE_ORDERS = (6, 12, 24, 48)
ECG_ELECTRODES_BY_DIMENSION = {
    "1D": {
        "E1": "(-0.5 0 0)",
        "E2": "(1.5 0 0)",
        "E3": "(1.2 0 0)",
        "E4": "(1.35 0 0)",
        "E5": "(1.65 0 0)",
    },
    "2D": {
        "E1": "(-0.5 0.5 0)",
        "E2": "(1.5 0.5 0)",
        "E3": "(1.2 0.23 0)",
        "E4": "(1.35 0.78 0)",
        "E5": "(0.18 1.35 0)",
    },
    "3D": {
        "E1": "(-0.5 0.5 0.5)",
        "E2": "(1.5 0.5 0.5)",
        "E3": "(1.2 0.23 0.61)",
        "E4": "(1.35 0.74 0.28)",
        "E5": "(1.55 0.41 0.83)",
        "S1_XP": "(1.050000 0.500000 0.500000)",
        "S1_XM": "(-0.050000 0.500000 0.500000)",
        "S1_YP": "(0.500000 1.050000 0.500000)",
        "S1_YM": "(0.500000 -0.050000 0.500000)",
        "S1_ZP": "(0.500000 0.500000 1.050000)",
        "S1_ZM": "(0.500000 0.500000 -0.050000)",
        "S1_DP": "(1.028868 1.028868 1.028868)",
        "S1_DM": "(-0.028868 -0.028868 -0.028868)",
        "S2_XP": "(1.100000 0.500000 0.500000)",
        "S2_XM": "(-0.100000 0.500000 0.500000)",
        "S2_YP": "(0.500000 1.100000 0.500000)",
        "S2_YM": "(0.500000 -0.100000 0.500000)",
        "S2_ZP": "(0.500000 0.500000 1.100000)",
        "S2_ZM": "(0.500000 0.500000 -0.100000)",
        "S2_DP": "(1.057735 1.057735 1.057735)",
        "S2_DM": "(-0.057735 -0.057735 -0.057735)",
        "S3_XP": "(1.200000 0.500000 0.500000)",
        "S3_XM": "(-0.200000 0.500000 0.500000)",
        "S3_YP": "(0.500000 1.200000 0.500000)",
        "S3_YM": "(0.500000 -0.200000 0.500000)",
        "S3_ZP": "(0.500000 0.500000 1.200000)",
        "S3_ZM": "(0.500000 0.500000 -0.200000)",
        "S3_DP": "(1.115470 1.115470 1.115470)",
        "S3_DM": "(-0.115470 -0.115470 -0.115470)",
        "S4_XP": "(1.350000 0.500000 0.500000)",
        "S4_XM": "(-0.350000 0.500000 0.500000)",
        "S4_YP": "(0.500000 1.350000 0.500000)",
        "S4_YM": "(0.500000 -0.350000 0.500000)",
        "S4_ZP": "(0.500000 0.500000 1.350000)",
        "S4_ZM": "(0.500000 0.500000 -0.350000)",
        "S4_DP": "(1.202073 1.202073 1.202073)",
        "S4_DM": "(-0.202073 -0.202073 -0.202073)",
        "S5_XP": "(1.500000 0.500000 0.500000)",
        "S5_XM": "(-0.500000 0.500000 0.500000)",
        "S5_YP": "(0.500000 1.500000 0.500000)",
        "S5_YM": "(0.500000 -0.500000 0.500000)",
        "S5_ZP": "(0.500000 0.500000 1.500000)",
        "S5_ZM": "(0.500000 0.500000 -0.500000)",
        "S5_DP": "(1.288675 1.288675 1.288675)",
        "S5_DM": "(-0.288675 -0.288675 -0.288675)",
        "S6_XP": "(1.750000 0.500000 0.500000)",
        "S6_XM": "(-0.750000 0.500000 0.500000)",
        "S6_YP": "(0.500000 1.750000 0.500000)",
        "S6_YM": "(0.500000 -0.750000 0.500000)",
        "S6_ZP": "(0.500000 0.500000 1.750000)",
        "S6_ZM": "(0.500000 0.500000 -0.750000)",
        "S6_DP": "(1.433013 1.433013 1.433013)",
        "S6_DM": "(-0.433013 -0.433013 -0.433013)",
        "S7_XP": "(2.000000 0.500000 0.500000)",
        "S7_XM": "(-1.000000 0.500000 0.500000)",
        "S7_YP": "(0.500000 2.000000 0.500000)",
        "S7_YM": "(0.500000 -1.000000 0.500000)",
        "S7_ZP": "(0.500000 0.500000 2.000000)",
        "S7_ZM": "(0.500000 0.500000 -1.000000)",
        "S7_DP": "(1.577350 1.577350 1.577350)",
        "S7_DM": "(-0.577350 -0.577350 -0.577350)",
    },
}
BLOCK_MESH_RESOLUTION_BY_DIMENSION = {
    "1D": "{cells} 1 1",
    "2D": "{cells} {cells} 1",
    "3D": "{cells} {cells} {cells}",
}
