"""``case_rendering.patch_mutation``, the one ``clone_and_patch`` resolver every
OpenFOAM-based plugin uses. It reads ``expected_blocks`` off a hex-cell-counts
parameter's key path, so a multi-block blockMeshDict gets the block count its
record declared instead of 1, and it renders typed container values as
OpenFOAM text.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.case_rendering import _target_for_parameter, patch_mutation
from omnidriver.openfoam.case_planning import HEX_CELL_COUNTS_KEY_PATH

OWNER = "org.test"

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
        owner=OWNER,
        document="system/blockMeshDict.3D",
        key_path=key_path,
        value=value,
        value_kind="integer_list",
        source="case",
    )


def test_a_hex_target_defaults_to_one_block_for_the_bare_key_path():
    parameter = _hex_cell_counts_parameter(key_path=HEX_CELL_COUNTS_KEY_PATH)

    target = _target_for_parameter(parameter)

    assert target["expected_blocks"] == 1
    assert target["hex_cell_counts"] == "20 20 20"


def test_a_hex_target_honours_an_explicit_block_count_from_the_key_path():
    parameter = _hex_cell_counts_parameter(key_path=("hex_cell_counts", "3"))

    target = _target_for_parameter(parameter)

    assert target["expected_blocks"] == 3
    assert target["hex_cell_counts"] == "20 20 20"


def test_patch_mutation_and_render_a_real_three_block_document(tmp_path: Path):
    """A key path declaring `expected_blocks=3` rewrites all three blocks."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict.3D").write_text(_THREE_HEX_BLOCK_DICT)

    parameter = ParameterAssignment(
        qualified_id="hex_cell_counts",
        owner=OWNER,
        document="system/blockMeshDict.3D",
        key_path=("hex_cell_counts", "3"),
        value=(20, 20, 20),
        value_kind="integer_list",
        source="case",
    )
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id=OWNER,
        workflow="test", source_artifacts=(), parameters=(parameter,), requested_by="test",
    )

    resolved = patch_mutation(request, owner_id=OWNER)
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )

    [file] = rendered
    assert file.path == "system/blockMeshDict.3D"
    assert file.content.decode().count("(20 20 20) simpleGrading") == 3


def test_patch_mutation_refuses_a_wrongly_declared_block_count(tmp_path: Path):
    """`expected_blocks=1` against a three-block document still refuses."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict.3D").write_text(_THREE_HEX_BLOCK_DICT)

    parameter = _hex_cell_counts_parameter(key_path=HEX_CELL_COUNTS_KEY_PATH)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id=OWNER,
        workflow="test", source_artifacts=(), parameters=(parameter,), requested_by="test",
    )

    resolved = patch_mutation(request, owner_id=OWNER)
    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )


@pytest.mark.parametrize("value_kind, value, rendered", [
    ("vector3", (1, 2.5, 3), "(1 2.5 3)"),
    ("word_list", ("a", "b"), "(a b)"),
    ("dimensioned_scalar", {"value": 75000, "dimensions": (0, -3, 0, 0, 0, 1, 0)}, "[0 -3 0 0 0 1 0] 75000"),
    ("boolean", True, True),
    ("scalar", 0.5, 0.5),
])
def test_a_typed_value_is_rendered_as_the_text_openfoam_reads(value_kind, value, rendered):
    parameter = ParameterAssignment(
        qualified_id="k", owner=OWNER, document="system/d", key_path=("k",), value=value, value_kind=value_kind, source="case",
    )

    assert _target_for_parameter(parameter)["value"] == rendered


def test_a_remove_carries_no_value_and_another_mode_is_refused(tmp_path: Path):
    removal = ParameterAssignment(
        qualified_id="k", owner=OWNER, document="system/d", key_path=("k",), value=None, value_kind="word", source="case", operation="remove",
    )
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=tmp_path, adapter_id=OWNER,
        workflow="test", source_artifacts=(), parameters=(removal,), requested_by="test",
    )

    (target,) = patch_mutation(request, owner_id=OWNER).targets
    assert target["operation"] == "remove" and "value" not in target
    with pytest.raises(ValueError, match="clone_and_patch"):
        patch_mutation(SimpleNamespace(mode="synthesize"), owner_id=OWNER)


def test_a_patch_against_a_missing_document_is_refused(tmp_path: Path):
    parameter = ParameterAssignment(
        qualified_id="deltaT", owner=OWNER, document="system/controlDict",
        key_path=("deltaT",), value=1e-4, value_kind="scalar", source="case",
    )
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=tmp_path, adapter_id=OWNER,
        workflow="test", source_artifacts=(), parameters=(parameter,), requested_by="test",
    )
    with pytest.raises(ValueError, match="system/controlDict"):
        case_rendering.render_patch_case_files(
            patch_mutation(request, owner_id=OWNER), snapshot_root=tmp_path / "scratch",
            driver_context=None, renderer_id="test",
        )
