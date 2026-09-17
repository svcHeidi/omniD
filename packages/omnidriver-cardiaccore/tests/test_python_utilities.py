import numpy as np
import pytest

from omnidriver.cardiaccore.operations.cobiveco import CARDIACCORE_COBIVECO_TARGET, normalize_cobiveco_coordinates, read_cobiveco_target_convention
from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.operations.vtu_selection import read_cell_ids, render_cell_set


def test_cobiveco_mapping_reverses_raw_transmural_sense_and_maps_chambers():
    result = normalize_cobiveco_coordinates(
        np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.array([0.2, 0.8]), target_convention=CARDIACCORE_COBIVECO_TARGET
    )
    assert result["uvc_transmural"].tolist() == [1.0, 0.0]
    assert result["uvc_intraventricular"].tolist() == [-1.0, 1.0]
    assert result["uvc_longitudinal"].tolist() == [0.2, 0.8]


def test_cobiveco_mapping_rejects_non_aligned_or_out_of_range_inputs():
    with pytest.raises(ValueError):
        normalize_cobiveco_coordinates(np.array([0]), np.array([0, 1]), np.array([0]), target_convention=CARDIACCORE_COBIVECO_TARGET)
    with pytest.raises(ValueError):
        normalize_cobiveco_coordinates(np.array([2]), np.array([0]), np.array([0]), target_convention=CARDIACCORE_COBIVECO_TARGET)


def test_cobiveco_mapping_rejects_a_target_convention_mismatch():
    with pytest.raises(ValueError, match="target convention"):
        normalize_cobiveco_coordinates(np.array([0]), np.array([0]), np.array([0]), target_convention={**CARDIACCORE_COBIVECO_TARGET, "transmural_endocardium": 1.0})


def test_discovered_operation_reads_selected_case_convention_before_calculation(tmp_path):
    dictionary = tmp_path / "system" / "coordinatesConventionDict"
    dictionary.parent.mkdir()
    dictionary.write_text(
        "coordinateSystem uvc; "
        "transmural { endocardium 0; epicardium 1; } "
        "intraventricularChambers { LV -1; RV 1; }"
    )
    operation = CardiacCorePlugin().get_named_catalogs()["cardiaccore_operations"]["cardiaccore.cobiveco.normalize.v1"]
    target = read_cobiveco_target_convention(tmp_path)
    assert operation["status"]["array_api"] == "available"
    assert normalize_cobiveco_coordinates(np.array([0]), np.array([1]), np.array([0.5]), target_convention=target)["uvc_transmural"].tolist() == [0.0]
    dictionary.write_text(
        "coordinateSystem uvc; "
        "transmural { endocardium 1; epicardium 0; } "
        "intraventricularChambers { LV -1; RV 1; }"
    )
    with pytest.raises(ValueError, match="target convention"):
        normalize_cobiveco_coordinates(np.array([0]), np.array([1]), np.array([0.5]), target_convention=read_cobiveco_target_convention(tmp_path))


def test_vtu_xml_selection_and_cellset_rendering(tmp_path):
    selection = tmp_path / "selection.vtu"
    selection.write_text("<VTKFile><UnstructuredGrid><Piece><CellData><DataArray Name=\"GlobalCellIds\">3 1 3</DataArray></CellData></Piece></UnstructuredGrid></VTKFile>")
    assert read_cell_ids(selection) == ("GlobalCellIds", [1, 3])
    rendered = render_cell_set("scar", [3, 1, 3])
    assert "object      scar;" in rendered
    assert "2\n(\n1\n3\n)" in rendered
