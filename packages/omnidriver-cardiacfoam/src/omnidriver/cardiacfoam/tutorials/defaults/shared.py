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
#     shared
#
# Description
#     Provides shared default parameters and constants for case generation.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path

from omnidriver.core.runtime.generic_case import (
    RUN_CASE_SCRIPT_RELPATH as _CORE_RUN_CASE_SCRIPT_RELPATH,
)


CONTROL_DICT_RELPATH = Path("system/controlDict")
ELECTRO_PROPERTIES_RELPATH = Path("constant/electroProperties")
# Re-exported from core rather than duplicated. This module used to carry
# its own literal naming the pre-migration monorepo layout
# (``applications/scripts/driverFoam/openfoam_driver/...``) -- a path that
# exists nowhere, and one that still spelled the retired ``openfoam_driver``
# package name. Every tutorial default below chains to this constant, so
# that copy, not core's, was the one on the live cardiac path.
RUN_CASE_SCRIPT_RELPATH = _CORE_RUN_CASE_SCRIPT_RELPATH
OUTPUT_DIR_NAME = "postProcessing"
OUTPUT_RELPATH = Path(OUTPUT_DIR_NAME)
