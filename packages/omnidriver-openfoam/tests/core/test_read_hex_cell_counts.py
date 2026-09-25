"""``case_planning.read_hex_cell_counts`` -- the ``ConfigValueCapability``
reader for the synthetic ``HEX_CELL_COUNTS_KEY_PATH`` (step 4a of
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §5).

Unit-level, against hand-built fixture text -- see
``test_axes_block_mesh_resolution_native.py``/
``test_record_key_validation_native.py`` (cardiacfoam package) for the same
reader wired through a real environment against the real native tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.case_planning import (
    HEX_CELL_COUNTS_KEY_PATH,
    read_hex_cell_counts,
)

_ONE_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 20 30) simpleGrading (1 1 1)\n"
    ");\n"
)

_TWO_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 20 30) simpleGrading (1 1 1)\n"
    "    hex (1 2 3 4 5 6 7 8) (10 20 30) simpleGrading (1 1 1)\n"
    ");\n"
)

_COMMENTED_AND_ONE_REAL_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    // hex (0 1 2 3 4 5 6 7) (40 6 14) simpleGrading (1 1 1)\n"
    "    hex (0 1 2 3 4 5 6 7) (200 30 70) simpleGrading (1 1 1)\n"
    ");\n"
)


def test_key_path_constant_is_a_one_element_tuple():
    assert HEX_CELL_COUNTS_KEY_PATH == ("hex_cell_counts",)


def test_reads_the_current_cell_counts_of_the_one_hex_block(tmp_path: Path):
    document = tmp_path / "blockMeshDict"
    document.write_text(_ONE_HEX_BLOCK_DICT)

    assert read_hex_cell_counts(document) == "10 20 30"


def test_skips_a_commented_out_hex_block(tmp_path: Path):
    """A real native file (restitutionCurves_s1s2Protocol's own
    blockMeshDict) comments out alternative resolutions with a leading
    `//` -- those must not be counted as real hex ( blocks."""
    document = tmp_path / "blockMeshDict"
    document.write_text(_COMMENTED_AND_ONE_REAL_HEX_BLOCK_DICT)

    assert read_hex_cell_counts(document) == "200 30 70"


def test_missing_document_reads_as_none(tmp_path: Path):
    document = tmp_path / "does_not_exist"

    assert read_hex_cell_counts(document) is None


def test_a_document_with_more_than_one_hex_block_is_refused_by_name(tmp_path: Path):
    document = tmp_path / "blockMeshDict"
    document.write_text(_TWO_HEX_BLOCK_DICT)

    with pytest.raises(KeyError, match="expected 1 hex"):
        read_hex_cell_counts(document)


def test_expected_blocks_can_be_overridden(tmp_path: Path):
    document = tmp_path / "blockMeshDict"
    document.write_text(_TWO_HEX_BLOCK_DICT)

    assert read_hex_cell_counts(document, expected_blocks=2) == "10 20 30"


def test_a_document_with_zero_hex_blocks_is_refused_by_name(tmp_path: Path):
    document = tmp_path / "blockMeshDict"
    document.write_text("FoamFile\n{\n}\nblocks\n(\n);\n")

    with pytest.raises(KeyError, match="expected 1 hex"):
        read_hex_cell_counts(document)


def test_dispatched_through_the_config_value_reader(tmp_path: Path):
    """The environment's `get_config_value_reader()` answer dispatches this
    synthetic key path to `read_hex_cell_counts` instead of `read_foam_entry`
    -- proven here without going through a real native file (that is
    `test_record_key_validation_native.py`'s job)."""
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    document = tmp_path / "blockMeshDict"
    document.write_text(_ONE_HEX_BLOCK_DICT)

    reader = OpenFOAMEnvironmentPlugin().get_config_value_reader()
    assert reader(document, HEX_CELL_COUNTS_KEY_PATH) == "10 20 30"
