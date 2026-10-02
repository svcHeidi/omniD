"""The context this adapter means when it means itself.

Inside cardiacFOAM's own modules, the caller isn't asking who the user
selected -- it's asking which dictionary vocabulary to validate against, which
is statically known. Asking the plugin registry instead makes the answer
depend on what else is installed (two adapters means no unique default, and
``build_electro_properties`` would raise ``LookupError``); see
``future/ENVIRONMENT_CONTRACT.md`` §12, the supplied-versus-discovered rule.
"""

from __future__ import annotations


def own_driver_context():
    """Build a ``DriverContext`` for cardiacFOAM without consulting the registry.

    Fresh per call -- a context is cheap and callers are entitled to mutate
    what they are given. Imports are function-local because
    ``cardiacfoam_plugin`` imports modules that call this helper.

    Composes the OpenFOAM environment adapter, which ``plugin.yaml`` declares
    under ``requires``: a single-provider stack here would make
    ``order_providers`` refuse every call for an unmet requirement.
    """
    from omnidriver.core.plugin_interface import driver_context
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    return driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="omnidriver.cardiacfoam",
    )


__all__ = ["own_driver_context"]
