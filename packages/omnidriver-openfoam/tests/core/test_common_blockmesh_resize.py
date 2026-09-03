import pytest

from omnidriver.openfoam.utils import replace_block_mesh_resolutions


def _write_template(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "FoamFile\n{\n    object blockMeshDict;\n}\n"
        "blocks\n(\n"
        "    hex (0 1 2 3 4 5 6 7) (10 10 10) simpleGrading (1 1 1)\n"
        ");\n"
    )


def test_replaces_single_hex_block_for_3d(tmp_path):
    path = tmp_path / "blockMeshDict"
    _write_template(path)
    replace_block_mesh_resolutions(path, "20 20 20")
    text = path.read_text()
    assert "hex (0 1 2 3 4 5 6 7) (20 20 20) simpleGrading (1 1 1)" in text


def test_replaces_single_hex_block_for_1d(tmp_path):
    path = tmp_path / "blockMeshDict"
    _write_template(path)
    replace_block_mesh_resolutions(path, "50 1 1")
    text = path.read_text()
    assert "hex (0 1 2 3 4 5 6 7) (50 1 1) simpleGrading (1 1 1)" in text


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        replace_block_mesh_resolutions(tmp_path / "missing", "20 20 20")


def test_missing_hex_line_raises(tmp_path):
    path = tmp_path / "blockMeshDict"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("FoamFile\n{\n}\n")
    with pytest.raises(KeyError, match="Expected to update"):
        replace_block_mesh_resolutions(path, "20 20 20")
