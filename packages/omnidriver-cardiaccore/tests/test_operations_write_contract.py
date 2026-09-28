"""Classifies each of the three writes in ``cardiaccore/operations/``
(found via ``grep -rn 'write_text\\|write_bytes\\|open(.*[\\"']w'``) as a
case input or a standalone export, and asserts the facts each
classification rests on."""
from __future__ import annotations

import inspect

from omnidriver.cardiaccore.operations import electrodes, vtu_selection


def test_write_cell_set_has_no_case_root_or_adapter_addressing():
    """A case input the channel would route needs a case_root and an
    addressed document/key_path (see `overrides.apply_input_overrides_planned`'s
    signature) -- `write_cell_set` has neither; it writes to whatever `path`
    the caller names, which is exactly why it is not migrated yet."""
    parameters = set(inspect.signature(vtu_selection.write_cell_set).parameters)
    assert parameters == {"path", "object_name", "ids"}
    assert "case_root" not in parameters


def test_write_cell_set_renders_a_real_cellset_foamfile():
    rendered = vtu_selection.render_cell_set("selectedCells", [3, 1, 2])
    assert "class       cellSet;" in rendered
    assert "object      selectedCells;" in rendered
    # Deterministic sorted IDs -- part of what makes this renderable through
    # a future channel renderer without inventing new ordering semantics.
    assert "1\n2\n3" in rendered


def test_electrode_writers_carry_no_case_relative_addressing():
    """Both electrode-bundle writers take an explicit `path` and a validated
    payload -- no `case_root`, no dictionary key, no driver_path. Nothing
    ties their output to a specific case document, which is the structural
    signal behind classifying them as standalone exports rather than case
    inputs."""
    for writer in (electrodes.write_reference_offset_bundle, electrodes.write_electrode_positions):
        parameters = set(inspect.signature(writer).parameters)
        assert "case_root" not in parameters
        assert "path" in parameters


def test_electrode_bundle_payloads_round_trip_without_dictionary_syntax(tmp_path):
    """A standalone export's payload is portable JSON, not OpenFOAM
    dictionary text -- confirming there is no dictionary key/value shape
    here for the channel's ParameterAssignment model to address at all."""
    import json

    bundle = {
        "source_heart_vtk": "heart.vtu",
        "source_coordinate_unit": "mm",
        "normalized_offsets": {"LA1": [0.1, 0.2, 0.3]},
    }
    path = tmp_path / "bundle.json"
    electrodes.write_reference_offset_bundle(path, bundle)
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == electrodes.ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION
    assert payload["source_heart_vtk"] == "heart.vtu"
