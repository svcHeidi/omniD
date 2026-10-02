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
#     named_catalogs
#
# Description
#     cardiacFoam's own named catalogs (ionic models, active-tension models),
#     exposed through the plugin's ``get_named_catalogs()`` hook and namespaced
#     generically under introspection's ``plugin_catalogs`` key -- core no
#     longer hardcodes the field names ``ionic_model_catalog``/
#     ``active_tension_catalog``. Kept as a plain function, not a method, so
#     both the plugin's real hook and the v1-compatibility fallback in
#     ``core/compatibility.py`` share one authored shape.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from typing import Any

from omnidriver.cardiacfoam.active_tension_catalog import ACTIVE_TENSION_MODEL_CATALOG
from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
from omnidriver.cardiacfoam.solver_coupling import SOLVER_COMPATIBILITY_RULES


def named_catalogs() -> dict[str, Any]:
    """Return the plugin's ionic-model and active-tension catalogs, unserialized
    (core owns serialization). The model dicts are copies: the live module
    catalogues are mutable, and ``IONIC_MODEL_CATALOG`` is written into at
    import."""
    return {
        "ionic_model_catalog": {
            "schema_version": "1.0",
            "ionic_models": dict(IONIC_MODEL_CATALOG),
            "solver_compatibility": list(SOLVER_COMPATIBILITY_RULES),
        },
        "active_tension_catalog": {
            "schema_version": "1.0",
            "active_tension_models": dict(ACTIVE_TENSION_MODEL_CATALOG),
        },
    }
