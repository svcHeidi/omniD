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
#     test_rtst_enum_contract
#
# Description
#     Tests rtst enum contract logic and specification contracts.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Contract test: catalogue ``enum_values`` match the registered
runtime-selection types in the native C++ source.

Drift is reported in four ways (``rtst_scanner.runtime_selection_report``):

* a catalogue enum's values diverge from the table it claims to expose;
* a catalogue enum is neither mapped to a table nor classified as a plain word;
* a table exists in the C++ with no catalogue mapping and no internal waiver;
* a mapping or waiver names something that no longer exists.

Corrected 2026-09-28: the mapping this test held as module constants
(``RTST_BY_DRIVER_PATH``, ``NON_RTST_DRIVER_PATHS``,
``INTERNAL_RTST_ALLOWLIST``) now lives in the plugin's reviewed allowlist
(``dict_key_allowlist.json``, ``runtime_selection``), because every strict
plan checks it too. The source root is the supplied one the plugin profile
declares (``cxx_mapping.source_root``), never a walk-up: this test was
``skip_without_monorepo`` and skipped silently everywhere, so 4 unclassified
enums had accumulated unseen when it first ran for real.
"""

from __future__ import annotations

import os

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.rtst_scanner import runtime_selection_report
import json

pytestmark = pytest.mark.native

_MAPPING = CardiacFoamPlugin.get_profile().cxx_mapping


@pytest.fixture(scope="module")
def report() -> dict:
    src_root = _MAPPING.source_root(os.environ)
    if src_root is None or not src_root.is_dir():
        pytest.fail(
            f"{_MAPPING.source_root_variable} must name the native cardiacFOAM tutorials "
            f"tree, whose {_MAPPING.source_root_relative} is the C++ source; got {src_root}"
        )
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:rtst")
    return runtime_selection_report(
        src_root,
        entries=context.capabilities.dictionaries.entries(),
        mapping=json.loads(_MAPPING.allowlist_path.read_text())["runtime_selection"],
    )


@pytest.mark.parametrize("drift", [
    "selector_drift",
    "unclassified_selector_enums",
    "unmapped_selector_bases",
    "unused_selector_mapping",
])
def test_catalogue_enums_agree_with_runtime_selection_tables(report, drift) -> None:
    assert report[drift] == [], (
        f"{drift}: {report[drift]}. Fix the catalogue, or review the "
        "runtime_selection mapping in dict_key_allowlist.json"
    )


def test_every_mapped_selector_has_registered_values(report) -> None:
    assert report["selector_values"]["$ELECTRO_MODEL_COEFFS.ionicModel"]
