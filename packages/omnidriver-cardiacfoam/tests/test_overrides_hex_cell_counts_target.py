"""``cardiacfoam.overrides._target_for_parameter``'s hex-cell-counts branch --
P2, 2026-09-26
(``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5e): "the writer... take[s] the block count through the patch instead of
defaulting to 1".

Before this task, `_target_for_parameter` always called
``plan_block_mesh_resolution(document, cell_counts_str)`` -- that planner's
OWN ``expected_blocks=1`` default, regardless of how many blocks the record
that produced the parameter actually declared. Correct for every
single-block document migrated so far, silently wrong for a multi-block one:
a real rewrite of ``manufacturedSolutions/bathBidomain``'s three-block
``blockMeshDict.<dim>`` files would have raised "Expected to update 1 hex
blocks, but found 3" regardless of what the axis resolved.

``_target_for_parameter`` now reads ``expected_blocks`` off
``parameter.key_path`` itself (``case_planning
.hex_cell_counts_expected_blocks``, the same grammar
``block_mesh_resolution_axis`` writes via ``hex_cell_counts_key_path``), so
the actual count the record declared reaches the renderer instead.
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
    """End to end: a `ParameterAssignment` whose key path declares
    `expected_blocks=3` reaches a real three-block document correctly --
    the exact write bathBidomain needs and the old code (implicitly
    `expected_blocks=1`) could never have performed without refusing."""
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
    """The contrast case: declaring `expected_blocks=1` (the OLD implicit
    default) against this same real three-block document still refuses --
    proving the fix is additive (a record that states the right count now
    works), not a loosening of the existing "wrong block count" guard."""
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
