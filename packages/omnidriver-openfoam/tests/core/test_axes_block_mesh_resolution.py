"""``block_mesh_resolution_axis`` -- the OpenFOAM package's one generic axis
(design doc ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
design.md`` §3, corrected 2026-09-25).

TDD: every test in this module failed before ``axes/block_mesh_resolution.py``
existed (``ModuleNotFoundError: No module named
'omnidriver.openfoam.axes.block_mesh_resolution'``), then failed again on the
first working draft that read the whole document instead of only checking
its existence -- see ``test_resolve_succeeds_against_a_document_with_more_
than_one_hex_block`` below, which pins the reason a document's hex-block
count is never checked here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ResolvedMutation
from omnidriver.core.tutorial_records import AxisContract, AxisResult
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.case_planning import plan_block_mesh_resolution, plan_delta_t

_ONE_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    ");\n"
)

_TWO_HEX_BLOCK_DICT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    "    hex (1 2 3 4 5 6 7 8) (10 1 1) simpleGrading (1 1 1)\n"
    ");\n"
)


def _staged_case(tmp_path: Path, document: str, content: str) -> Path:
    case_root = tmp_path / "case"
    target = case_root / document
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return case_root


# ---------------------------------------------------------------------------
# The builder itself
# ---------------------------------------------------------------------------


def test_builder_returns_an_axis_contract_declaring_an_integer_study_value():
    axis = block_mesh_resolution_axis(
        "my_axis", document="system/blockMeshDict", resolution=lambda n: (n, n, n),
    )
    assert isinstance(axis, AxisContract)
    assert axis.name == "my_axis"
    assert axis.value_kind == "integer"
    assert callable(axis.resolve)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_resolve_produces_the_planners_hex_cell_counts_patch(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict", resolution=lambda n: (n, n, n),
    )

    result = axis.resolve(20, case_root)

    assert isinstance(result, AxisResult)
    assert result.command_arguments == {}
    assert len(result.patches) == 1
    patch = result.patches[0]
    assert patch.document == "system/blockMeshDict"
    assert patch.key_path == ("hex_cell_counts",)
    # The exact string `plan_block_mesh_resolution` itself would produce --
    # reused, not duplicated.
    assert patch.value == plan_block_mesh_resolution(
        "system/blockMeshDict", "20 20 20",
    )["hex_cell_counts"]
    assert patch.value == "20 20 20"


def test_resolve_supports_a_non_isotropic_resolution_formula(tmp_path):
    """`resolution` is the record's own pure formula -- this axis does not
    assume it is always `lambda n: (n, n, n)`."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "cable_cells", document="system/blockMeshDict",
        resolution=lambda n: (n, 1, 1),
    )

    result = axis.resolve(50, case_root)

    assert result.patches[0].value == "50 1 1"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_resolve_refuses_a_non_integer_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict",
        resolution=lambda n: (n, n, "20"),
    )

    with pytest.raises(ValueError, match="must return a tuple of 3 integers"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_boolean_masquerading_as_an_integer_count(tmp_path):
    """`bool` is an `int` subclass in Python -- `True`/`False` must still be
    refused, not silently accepted as 1/0."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict",
        resolution=lambda n: (n, n, True),
    )

    with pytest.raises(ValueError, match="must return a tuple of 3 integers"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_non_positive_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict",
        resolution=lambda n: (0, n, n),
    )

    with pytest.raises(ValueError, match="non-positive cell count"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_negative_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict",
        resolution=lambda n: (-5, n, n),
    )

    with pytest.raises(ValueError, match="non-positive cell count"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_document_that_does_not_exist_in_the_staged_case(tmp_path):
    case_root = tmp_path / "case"
    case_root.mkdir()
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict", resolution=lambda n: (n, n, n),
    )

    with pytest.raises(ValueError, match="does not exist in the staged case"):
        axis.resolve(20, case_root)


def test_resolve_reads_nothing_but_existence_before_refusing_a_bad_count(tmp_path):
    """The count is validated BEFORE any file access -- a bad `resolution`
    output is refused even when the document does not exist at all, so the
    refusal message names the count, not a spurious "missing document"."""
    case_root = tmp_path / "case"
    case_root.mkdir()  # the document itself is never created
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict",
        resolution=lambda n: (n, n, "bad"),
    )

    with pytest.raises(ValueError, match="must return a tuple of 3 integers"):
        axis.resolve(20, case_root)


# ---------------------------------------------------------------------------
# The deferred "exactly one hex block" refusal: reused, not duplicated.
#
# `plan_block_mesh_resolution` itself never checks a document's real hex-
# block count (case_planning.py's own docstring: "That check is the
# renderer's job") -- only `_rewrite_hex_block_lines`, called by
# `case_rendering.render_patch_case_files`, does. This axis therefore never
# refuses a multi-block document at resolve() time either: it must not, since
# a real multi-block file (bathBidomain's own `blockMeshDict.3D`, proven by
# this package's native tests) is a legitimate document to compute a patch
# value for. The refusal still exists -- it fires wherever this patch is
# actually rendered, reusing the exact mechanism `test_block_mesh_resolution_
# channel.py` already characterizes against a real fixture.
# ---------------------------------------------------------------------------


def test_resolve_succeeds_against_a_document_with_more_than_one_hex_block(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict", resolution=lambda n: (n, n, n),
    )

    result = axis.resolve(20, case_root)

    assert result.patches[0].value == "20 20 20"


def test_the_axis_produced_value_still_refuses_the_wrong_block_count_when_rendered(tmp_path):
    """The patch's value threads straight back into `plan_block_mesh_
    resolution`'s own default `expected_blocks=1` -- rendering it against the
    real two-block document above refuses via the SAME reused mechanism,
    proving the check was deferred, not dropped."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", document="system/blockMeshDict", resolution=lambda n: (n, n, n),
    )
    patch = axis.resolve(20, case_root).patches[0]

    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    (case_root / "system" / "controlDict").write_text("FoamFile\n{\n}\ndeltaT 1e-05;\n")
    resolved = ResolvedMutation(
        request=request,
        targets=(
            {
                "document": delta_t.document,
                "expanded_key_path": list(delta_t.expanded_key_path()),
                "value": delta_t.value,
                "format": "openfoam_dictionary",
            },
            plan_block_mesh_resolution(patch.document, patch.value),
        ),
        preconditions=(), expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )

    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )
