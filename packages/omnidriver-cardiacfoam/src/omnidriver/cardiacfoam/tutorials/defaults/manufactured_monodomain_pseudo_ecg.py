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
        "S1_P1": "(0.390980 0.780400 1.043750)",
        "S1_P2": "(1.035003 0.236031 0.977646)",
        "S1_P3": "(-0.044504 0.341492 0.729406)",
        "S1_P4": "(0.829487 1.042398 0.579956)",
        "S1_P5": "(0.608788 -0.048661 0.429530)",
        "S1_P6": "(-0.037359 0.894624 0.230308)",
        "S1_P7": "(1.038803 0.558528 0.066075)",
        "S1_P8": "(0.301407 0.274012 -0.043750)",
        "S2_P1": "(0.382209 0.802961 1.087500)",
        "S2_P2": "(1.070005 0.218761 1.008896)",
        "S2_P3": "(-0.089008 0.328536 0.748156)",
        "S2_P4": "(0.855243 1.084796 0.586206)",
        "S2_P5": "(0.618436 -0.097321 0.423280)",
        "S2_P6": "(-0.074719 0.922060 0.211558)",
        "S2_P7": "(1.077606 0.562743 0.034825)",
        "S2_P8": "(0.285429 0.255829 -0.087500)",
        "S3_P1": "(0.364665 0.848083 1.175000)",
        "S3_P2": "(1.140010 0.184220 1.071396)",
        "S3_P3": "(-0.178016 0.302626 0.785656)",
        "S3_P4": "(0.906753 1.169592 0.598706)",
        "S3_P5": "(0.637733 -0.194642 0.410780)",
        "S3_P6": "(-0.149437 0.976932 0.174058)",
        "S3_P7": "(1.155212 0.571173 -0.027675)",
        "S3_P8": "(0.253471 0.219464 -0.175000)",
        "S4_P1": "(0.338350 0.915765 1.306250)",
        "S4_P2": "(1.245018 0.132410 1.165146)",
        "S4_P3": "(-0.311527 0.263760 0.841906)",
        "S4_P4": "(0.984019 1.296787 0.617456)",
        "S4_P5": "(0.666678 -0.340624 0.392030)",
        "S4_P6": "(-0.261515 1.059239 0.117808)",
        "S4_P7": "(1.271621 0.583818 -0.121425)",
        "S4_P8": "(0.205535 0.164915 -0.306250)",
        "S5_P1": "(0.312035 0.983448 1.437500)",
        "S5_P2": "(1.350025 0.080599 1.258896)",
        "S5_P3": "(-0.445039 0.224894 0.898156)",
        "S5_P4": "(1.061285 1.423981 0.636206)",
        "S5_P5": "(0.695623 -0.486605 0.373280)",
        "S5_P6": "(-0.373593 1.141546 0.061558)",
        "S5_P7": "(1.388030 0.596464 -0.215175)",
        "S5_P8": "(0.157599 0.110366 -0.437500)",
        "S6_P1": "(0.268177 1.096253 1.656250)",
        "S6_P2": "(1.525038 -0.005752 1.415146)",
        "S6_P3": "(-0.667558 0.160117 0.991906)",
        "S6_P4": "(1.190062 1.635972 0.667456)",
        "S6_P5": "(0.743864 -0.729908 0.342030)",
        "S6_P6": "(-0.560389 1.278725 -0.032192)",
        "S6_P7": "(1.582045 0.617539 -0.371425)",
        "S6_P8": "(0.077706 0.019452 -0.656250)",
        "S7_P1": "(0.224318 1.209057 1.875000)",
        "S7_P2": "(1.700051 -0.092103 1.571396)",
        "S7_P3": "(-0.890078 0.095340 1.085656)",
        "S7_P4": "(1.318839 1.847962 0.698706)",
        "S7_P5": "(0.792106 -0.973211 0.310780)",
        "S7_P6": "(-0.747185 1.415904 -0.125942)",
        "S7_P7": "(1.776060 0.638614 -0.527675)",
        "S7_P8": "(-0.002188 -0.071463 -0.875000)",
    },
}
BLOCK_MESH_RESOLUTION_BY_DIMENSION = {
    "1D": "{cells} 1 1",
    "2D": "{cells} {cells} 1",
    "3D": "{cells} {cells} {cells}",
}
