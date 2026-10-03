"""The versioned sweep-spec JSON Schema."""
from __future__ import annotations

import json
from importlib.resources import files

import jsonschema
import pytest

from omnidriver.core.sweep.sweep_expansion import (
    SweepValidationError,
    check_case_count_cap,
    expand_sweep,
)


def load_sweep_spec_schema() -> dict:
    return json.loads(files("omnidriver.schemas").joinpath("sweep-spec.schema.json").read_text())


#: AGENT_GUIDE.md, "Sweeping a parameter grid" (generic/from-scratch mode).
GENERIC_MODE_EXAMPLE = {
    "base": {
        "electro_selectors": {
            "myocardiumSolver": "singleCellSolver",
            "tissue": "epicardialCells",
        },
        "physics_selectors": {"type": "electroModel"},
    },
    "sweep": {
        "mode": "cross_product",
        "independent": {
            "ionicModel": ["TNNP", "BuenoOrovio"],
            "deltaT": [1e-6, 2e-6],
        },
        "dependent": [
            {"name": "caseId", "derive": "case_id_template", "of": ["ionicModel", "deltaT"]}
        ],
    },
}

#: AGENT_GUIDE.md, "Sweeping an existing registered tutorial (base.entry)".
ENTRY_MODE_EXAMPLE = {
    "base": {
        "entry": "niederer2011",
        "solvers": ["implicit"],
        "end_time_by_dx": {"0.5": 0.2, "0.2": 0.08, "0.1": 0.055},
    },
    "sweep": {
        "mode": "zip",
        "independent": {
            "dx_values": [[0.5], [0.2], [0.2], [0.2], [0.1], [0.1], [0.1]],
            "dt_values": [[0.01], [0.01], [0.005], [0.001], [0.01], [0.005], [0.001]],
        },
        "dependent": [
            {
                "name": "output_dir_name",
                "derive": "output_dir_name_template",
                "of": ["dx_values", "dt_values"],
            }
        ],
    },
}

IN_TREE_SWEEP_SPECS = {
    "agent_guide_generic_mode": GENERIC_MODE_EXAMPLE,
    "agent_guide_entry_mode": ENTRY_MODE_EXAMPLE,
}


def test_every_in_tree_sweep_spec_validates():
    schema = load_sweep_spec_schema()
    for name, spec in IN_TREE_SWEEP_SPECS.items():
        jsonschema.validate(spec, schema)
        # And the code actually accepts it (cap check only -- expand_sweep
        # itself needs a get_derivation lookup for "dependent", which is
        # caller-supplied and out of this schema test's scope).
        check_case_count_cap(spec)


def test_a_spec_the_code_rejects_fails_the_schema_too():
    bad = {"sweep": {"mode": "banana", "independent": {"x": [1]}}}
    with pytest.raises(SweepValidationError):
        check_case_count_cap(bad)
    schema = load_sweep_spec_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_missing_sweep_key_fails_the_schema():
    schema = load_sweep_spec_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({}, schema)


def test_the_schema_is_readable_from_an_installed_wheel():
    """A repository-only schema file is absent from every wheel."""
    assert load_sweep_spec_schema()["$schema"]


def test_the_schema_carries_a_version():
    schema_id = load_sweep_spec_schema()["$id"]
    assert schema_id.rsplit("/", 1)[-1] == "v1"
