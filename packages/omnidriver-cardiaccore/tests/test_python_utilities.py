import numpy as np
import pytest

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.operations.vtu_selection import read_cell_ids, render_cell_set


def test_vtu_xml_selection_and_cellset_rendering(tmp_path):
    selection = tmp_path / "selection.vtu"
    selection.write_text("<VTKFile><UnstructuredGrid><Piece><CellData><DataArray Name=\"GlobalCellIds\">3 1 3</DataArray></CellData></Piece></UnstructuredGrid></VTKFile>")
    assert read_cell_ids(selection) == ("GlobalCellIds", [1, 3])
    rendered = render_cell_set("scar", [3, 1, 3])
    assert "object      scar;" in rendered
    assert "2\n(\n1\n3\n)" in rendered
