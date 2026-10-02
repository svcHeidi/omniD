"""An override that validates but emits nothing is the worst defect class here.

Every catalogued entry is set and must emit at the right nesting: a whole-catalog sweep, because hand-picked examples miss entries."""

from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.case_builder import (
    build_electro_properties,
    select_applicable_entries,
)

# Selector contexts to try. An entry only has to emit under ONE of them, since
# many are gated by applicable_when on the solver.
_CONTEXTS = (
    {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
    {"myocardiumSolver": "bidomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
    {"myocardiumSolver": "singleCellSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
    {"myocardiumSolver": "eikonalSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
)

_COEFFS_PREFIX = "$ELECTRO_MODEL_COEFFS."

# A plausible value per value_kind. The point is emission, not validity, so
# these only need to survive the builder.
_VALUES = {
    "scalar": "1.5",
    "integer": "3",
    "boolean": "yes",
    "word": "probeValue",
    "word_list": "(alpha beta)",
    "scalar_list": "(1 2 3)",
    "integer_list": "(0 1 2)",
    "vector3": "(1 0 0)",
    "vector3_list": "((1 0 0) (0 1 0))",
    "dimensioned_scalar": "[0 0 0 0 0 0 0] 1.0",
    "dimensioned_tensor": "[0 0 0 0 0 0 0] (1 0 0 1 0 1)",
}


def _concrete_path(driver_path: str) -> str:
    """Substitute each <placeholder> with a distinct concrete instance name."""
    import re

    counter = {"n": 0}

    def _sub(_match):
        counter["n"] += 1
        return f"probe{counter['n']}"

    return re.sub(r"<[A-Za-z_][A-Za-z0-9_]*>", _sub, driver_path)


def _value_for(entry) -> str:
    if entry.enum_values:
        return entry.enum_values[0]
    if entry.typical_value:
        return entry.typical_value
    return _VALUES.get(entry.value_kind, "1.0")


def _electro_entries():
    context = _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:override_round_trip",
    )
    catalog = context.stack.call("get_dictionary_catalog")
    return [
        entry
        for entry in catalog.entries_for("electroProperties")
        if entry.driver_path.startswith(_COEFFS_PREFIX)
    ]


def _emit_with(entry, selectors):
    """Return (text, rejected); a builder refusal is loud, so it is not a silent drop."""
    path = _concrete_path(entry.driver_path)
    try:
        return (
            build_electro_properties(
                selectors=dict(selectors), overrides={path: _value_for(entry)}
            ),
            False,
        )
    except Exception:  # noqa: BLE001 - a refusal is a valid outcome here
        return (None, True)


def _leaf(driver_path: str) -> str:
    return _concrete_path(driver_path).split(".")[-1]


@pytest.mark.parametrize("entry", _electro_entries(), ids=lambda e: e.driver_path)
def test_an_accepted_override_is_never_silently_dropped(entry):
    """Emitting or being refused (common for multi-key entries set alone) is fine; only silence is a defect."""
    leaf = _leaf(entry.driver_path)
    accepted_but_absent = []

    for selectors in _CONTEXTS:
        # An entry gated by applicable_when is correctly absent from a context
        # that fails its gate; ask the driver's own predicate.
        context = dict(selectors)
        context[_concrete_path(entry.driver_path)] = _value_for(entry)
        if entry not in select_applicable_entries(context, entries=[entry]):
            continue

        text, rejected = _emit_with(entry, selectors)
        if rejected:
            continue
        if leaf in text:
            return
        accepted_but_absent.append(selectors["myocardiumSolver"])

    if accepted_but_absent:
        pytest.fail(
            f"{entry.driver_path} was ACCEPTED without complaint under "
            f"{accepted_but_absent} and emitted nothing. An agent setting it "
            f"would be told it succeeded while the dictionary stayed unchanged "
            f"-- the defect class that made cellZone and the ionic constant "
            f"overrides inert."
        )
    # Refused under every context: loud, therefore acceptable.


@pytest.mark.parametrize("entry", _electro_entries(), ids=lambda e: e.driver_path)
def test_coeffs_entries_land_inside_the_coeffs_block(entry):
    """Emitted at the file root, a Coeffs entry parses fine and the solver silently ignores it."""
    leaf = _leaf(entry.driver_path)
    for selectors in _CONTEXTS:
        text, rejected = _emit_with(entry, selectors)
        if rejected or leaf not in text:
            continue
        coeffs_block = f"{selectors['myocardiumSolver']}Coeffs"
        assert coeffs_block in text, f"no coeffs block emitted for {entry.driver_path}"
        assert text.index(leaf) > text.index(coeffs_block), (
            f"{entry.driver_path} was emitted at the electroProperties ROOT, "
            f"before {coeffs_block}. The solver reads it from inside the coeffs "
            f"block, so it would be silently ignored."
        )
        return
