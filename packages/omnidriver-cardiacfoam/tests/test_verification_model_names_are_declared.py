"""A predicate may not gate on a verifier the catalogue does not declare: every
``applicable_when`` verificationModel.type name must be in that key's
``enum_values``. An internal-consistency check, so it needs no native tree.
"""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:verification_model_names")

_TYPE_KEY_SUFFIX = "verificationModel.type"


def _declared_types() -> dict[str, frozenset[str]]:
    """Selectable model names, keyed by the driver path that declares them."""
    return {
        entry.driver_path: frozenset(entry.enum_values)
        for entry in _CTX.stack.call("get_dict_entries")
        if entry.driver_path.endswith(_TYPE_KEY_SUFFIX) and entry.enum_values
    }


def test_every_gated_verifier_name_is_selectable() -> None:
    declared = _declared_types()
    assert declared, "no verificationModel.type entry declares its enum_values"

    offenders: list[str] = []
    for entry in _CTX.stack.call("get_dict_entries"):
        for key, value in (entry.applicable_when or {}).items():
            if not key.endswith(_TYPE_KEY_SUFFIX):
                continue
            names = value if isinstance(value, tuple) else (value,)
            allowed = declared.get(key)
            if allowed is None:
                offenders.append(
                    f"{entry.driver_path}\n      gates on {key!r}, which no entry declares"
                )
                continue
            for name in names:
                if name not in allowed:
                    offenders.append(
                        f"{entry.driver_path}\n      gates on {name!r}, which is not in "
                        f"{key}'s enum_values"
                    )

    assert offenders == [], (
        "these entries gate on a verification model no case can select, so they "
        "are inapplicable to every case and nothing says so:\n  "
        + "\n  ".join(offenders)
        + "\n\nEither the predicate names a renamed or deleted verifier, or the "
        "enum_values of the type key are missing one."
    )
