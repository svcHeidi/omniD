"""cardiacFoam's named catalogs (ionic and active-tension models), exposed through ``get_named_catalogs()``."""

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
