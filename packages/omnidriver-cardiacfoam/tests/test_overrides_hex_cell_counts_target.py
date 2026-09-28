"""``overrides._target_for_parameter`` reads ``expected_blocks`` off the parameter's
key path (``case_planning.hex_cell_counts_expected_blocks``), so a multi-block
blockMeshDict gets the block count its record declared instead of 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment
from omnidriver.cardiacfoam.overrides import PLUGIN_ID, _target_for_parameter, resolve_patch_mutation
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.case_planning import HEX_CELL_COUNTS_KEY_PATH

_THREE_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 5 4 8 9 13 12) (80 80 80) simpleGrading (1 1 1)\n"
    "    hex (1 2 6 5 9 10 14 13) (80 80 80) simpleGrading (1 1 1)\n"
    "    hex (2 3 7 6 10 11 15 14) (80 80 80) simpleGrading (1 1 1)\n"
    ");\n"
)


def _hex_cell_counts_parameter(*, key_path, value=(20, 20, 20)) -> ParameterAssignment:
    return ParameterAssignment(
        qualified_id="hex_cell_counts",
        owner=PLUGIN_ID,
        document="system/blockMeshDict.3D",
        key_path=key_path,
        binding={},
        value=value,
        value_kind="integer_list",
        source="case",
    )


def test_target_for_parameter_defaults_to_one_block_for_the_bare_key_path():
    parameter = _hex_cell_counts_parameter(key_path=HEX_CELL_COUNTS_KEY_PATH)

    target = _target_for_parameter(parameter)

    assert target["expected_blocks"] == 1
    assert target["hex_cell_counts"] == "20 20 20"


def test_target_for_parameter_honours_an_explicit_block_count_from_the_key_path():
    parameter = _hex_cell_counts_parameter(key_path=("hex_cell_counts", "3"))

    target = _target_for_parameter(parameter)

    assert target["expected_blocks"] == 3
    assert target["hex_cell_counts"] == "20 20 20"


def test_resolve_patch_mutation_and_render_a_real_three_block_document(tmp_path: Path):
    """A key path declaring `expected_blocks=3` rewrites all three blocks."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict.3D").write_text(_THREE_HEX_BLOCK_DICT)

    parameter = ParameterAssignment(
        qualified_id="hex_cell_counts",
        owner=PLUGIN_ID,
        document="system/blockMeshDict.3D",
        key_path=("hex_cell_counts", "3"),
        binding={},
        value=(20, 20, 20),
        value_kind="integer_list",
        source="case",
    )
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id=PLUGIN_ID,
        workflow="test", source_artifacts=(), parameters=(parameter,), requested_by="test",
    )

    resolved = resolve_patch_mutation(request)
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )

    [file] = rendered
    assert file.path == "system/blockMeshDict.3D"
    assert file.content.decode().count("(20 20 20) simpleGrading") == 3


def test_resolve_patch_mutation_refuses_a_wrongly_declared_block_count(tmp_path: Path):
    """`expected_blocks=1` against a three-block document still refuses."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict.3D").write_text(_THREE_HEX_BLOCK_DICT)

    parameter = _hex_cell_counts_parameter(key_path=HEX_CELL_COUNTS_KEY_PATH)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id=PLUGIN_ID,
        workflow="test", source_artifacts=(), parameters=(parameter,), requested_by="test",
    )

    resolved = resolve_patch_mutation(request)
    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )
