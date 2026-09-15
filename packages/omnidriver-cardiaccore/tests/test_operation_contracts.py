"""Exercise the public discovery-to-call path, including packaged guidance."""

import importlib
import inspect
import json

import numpy as np
import pytest

from omnidriver.cardiaccore import CardiacCorePlugin
from omnidriver.cardiaccore.agent_guidance import read_guidance


def _resolve(reference):
    module, name = reference.split(":")
    return getattr(importlib.import_module(module), name)


def test_advertised_operations_have_resolvable_interfaces():
    catalogs = CardiacCorePlugin().get_named_catalogs()
    json.dumps(catalogs["cardiaccore_operations"])
    for operation_id, operation in catalogs["cardiaccore_operations"].items():
        assert operation["id"] == operation_id
        for field in ("purpose", "applicability", "preconditions", "evidence", "example"):
            assert operation[field], (operation_id, field)
        assert set(operation["failure_conditions"]) == {
            "invalid_input", "missing_capability", "scientific_interpretation",
        }
        assert operation["callable"] in {
            entry["callable"] for entry in operation["entrypoints"].values()
        }
        for entry in operation["entrypoints"].values():
            function = _resolve(entry["callable"])
            assert callable(function)
            assert set(entry["inputs"]) == set(inspect.signature(function).parameters)
            assert entry["outputs"] and entry["side_effects"]


def test_discovered_cobiveco_calls_check_the_actual_case_without_writes(tmp_path):
    dictionary = tmp_path / "system" / "uvcConventionDict"
    dictionary.parent.mkdir()
    original = "transmural { min 0; max 1; } intraventricularChambers { LV -1; RV 1; }"
    dictionary.write_text(original)
    operation = CardiacCorePlugin().get_named_catalogs()["cardiaccore_operations"][
        "cardiaccore.cobiveco.normalize.v1"
    ]
    read = _resolve(operation["entrypoints"]["read_target"]["callable"])
    calculate = _resolve(operation["callable"])
    result = calculate([0, 1], [1, 0], [0.2, 0.8], target_convention=read(tmp_path))
    assert result["uvc_transmural"].tolist() == [0, 1]
    assert dictionary.read_text() == original
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()] == [
        "system/uvcConventionDict",
    ]
    dictionary.write_text(original.replace("min 0; max 1", "min 1; max 0"))
    with pytest.raises(ValueError, match="target convention"):
        calculate([0], [1], [0.2], target_convention=read(tmp_path))


def test_guidance_is_readable_and_catalogs_are_independent_snapshots():
    plugin = CardiacCorePlugin()
    catalogs = plugin.get_named_catalogs()
    guide = catalogs["cardiaccore_agent_guidance"]
    reader = _resolve(guide["reader"])
    for role, record in guide["roles"].items():
        assert reader(role) == read_guidance(role)
        assert set(record["required_catalogs"]) <= catalogs.keys()
    with pytest.raises(ValueError, match="Unknown"):
        reader("../../README")
    operation_id = "cardiaccore.cobiveco.normalize.v1"
    catalogs["cardiaccore_operations"][operation_id]["status"]["array_api"] = "broken"
    fresh = plugin.get_named_catalogs()
    assert fresh["cardiaccore_operations"][operation_id]["status"]["array_api"] == "available"
    for index in fresh["cardiaccore_python_utilities"].values():
        assert index["use"] == fresh["cardiaccore_operations"][index["operation_id"]]["purpose"]


@pytest.mark.parametrize("bad", [0.0, [[0.0]], [float("nan")]])
def test_cobiveco_rejects_invalid_array_contract(bad):
    from omnidriver.cardiaccore.operations.cobiveco import (
        CARDIACCORE_COBIVECO_TARGET, normalize_cobiveco_coordinates,
    )
    with pytest.raises(ValueError):
        normalize_cobiveco_coordinates(bad, [0], [0], target_convention=CARDIACCORE_COBIVECO_TARGET)


@pytest.mark.parametrize("points", [[[0, 0]], [[float("nan"), 0, 0]], [[float("inf"), 0, 0]]])
def test_frame_rejects_invalid_coordinates_before_calculation(points):
    from omnidriver.cardiaccore.operations.electrodes import compute_lv_frame

    with pytest.raises(ValueError, match="Nx3|finite"):
        compute_lv_frame(np.asarray(points), [-1], [0])


def test_appended_vtu_does_not_silently_become_an_empty_selection(tmp_path, monkeypatch):
    from omnidriver.cardiaccore.operations import vtu_selection

    path = tmp_path / "selection.vtu"
    path.write_text('<VTKFile><UnstructuredGrid><Piece><CellData>'
                    '<DataArray Name="GlobalCellIds" format="appended" offset="0" />'
                    '</CellData></Piece></UnstructuredGrid></VTKFile>')
    monkeypatch.setattr(vtu_selection, "_read_with_pyvista", lambda path: {"GlobalCellIds": [9, 2]})
    assert vtu_selection.read_cell_ids(path) == ("GlobalCellIds", [2, 9])


@pytest.mark.parametrize("ids", [[-1], [1.5], [float("nan")]])
def test_cell_set_rejects_invalid_ids_without_writing(tmp_path, ids):
    from omnidriver.cardiaccore.operations.vtu_selection import write_cell_set

    path = tmp_path / "selection"
    with pytest.raises(ValueError, match="cell ID"):
        write_cell_set(path, "selection", ids)
    assert not path.exists()
