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
#     test_ionic_catalog_live_verification
#
# Description
#     Runs listCellModelsVariables for every catalogued ionic model and
#     asserts the catalog matches. Skipped when OpenFOAM is not sourced.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""The live ratchet: does IONIC_MODEL_CATALOG match the built solver?

An unknown ``ionicConstantOverrides`` name is a FatalError at solver startup (genericWriter's ionicModelIO), and
constant naming follows no static rule (``AC_`` for most, unprefixed for TNNP/BuenoOrovio, mixed in TWorld)."""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.ionic_catalog_verification import (
    find_listCellModelsVariables_binary,
    verify_ionic_catalog,
)
from omnidriver.cardiacfoam.ionic_model_catalog import (
    IONIC_MODEL_CATALOG,
)

requires_utility = pytest.mark.skipif(
    find_listCellModelsVariables_binary() is None,
    reason=(
        "listCellModelsVariables not on PATH -- source the OpenFOAM bashrc to "
        "run the live catalog check. This is a SKIP, not a pass."
    ),
)


@requires_utility
def test_every_catalogued_ionic_model_matches_the_built_solver():
    """A runtime-only name is invisible to an agent; a catalog-only name fatals the solver at startup."""
    result = verify_ionic_catalog()

    assert result.utility_available is True
    assert set(result.results) == set(IONIC_MODEL_CATALOG)

    problems = {
        name: {
            "status": model.status,
            "runtime_has_catalog_lacks": {
                k: list(v) for k, v in model.missing_from_catalog.items()
            },
            "catalog_has_runtime_lacks": {
                k: list(v) for k, v in model.extra_in_catalog.items()
            },
            "reason": model.reason,
        }
        for name, model in sorted(result.results.items())
        if model.status != "match"
    }
    assert not problems, (
        "IONIC_MODEL_CATALOG disagrees with the built solver.\n"
        "Regenerate the affected entries from listCellModelsVariables rather "
        "than editing them by hand -- the naming convention differs per model "
        "and cannot be inferred.\n"
        f"{problems}"
    )
    assert result.all_match is True


@requires_utility
def test_every_model_can_actually_be_instantiated():
    """Reported apart from name drift, so a broken case-synthesis path is not mistaken for it."""
    result = verify_ionic_catalog()
    errored = {
        name: model.reason
        for name, model in sorted(result.results.items())
        if model.status == "error"
    }
    assert not errored, f"models the solver would not instantiate: {errored}"
