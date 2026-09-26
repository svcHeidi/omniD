"""``block_mesh_resolution_axis`` -- the OpenFOAM package's one generic axis
(design doc ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
design.md`` §3, corrected 2026-09-25; extended 2026-09-26, P2,
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5e, to several documents and several ``hex (`` blocks).

TDD: every test in this module failed before ``axes/block_mesh_resolution.py``
existed (``ModuleNotFoundError: No module named
'omnidriver.openfoam.axes.block_mesh_resolution'``), then failed again on the
first working draft that read the whole document instead of only checking
its existence -- see ``test_resolve_succeeds_against_a_document_with_more_
than_one_hex_block`` below.

**Corrected 2026-09-26 (P2).** ``document`` (one path) became ``documents``
(one or more); ``expected_blocks`` became a required, per-axis-instance
argument instead of each downstream reader/writer independently defaulting
it to 1; ``resolution`` now takes the study value AND the document's own
current cell counts. Every test below that built an axis with the old
``document=``/one-argument-``resolution`` signature is rewritten for the
new one; several new tests exercise what changed (``expected_blocks``
threading through the patch's key path, several documents, and a
document's current counts reaching ``resolution``).
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

_TWO_HEX_BLOCK_DICT_DISAGREEING = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    "    hex (1 2 3 4 5 6 7 8) (10 1 2) simpleGrading (1 1 1)\n"
    ");\n"
)


def _staged_case(tmp_path: Path, document: str, content: str) -> Path:
    case_root = tmp_path / "case"
    target = case_root / document
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return case_root


def _isotropic(n, current, extents=None):
    del current, extents
    return (n, n, n)


# ---------------------------------------------------------------------------
# The builder itself: build-time refusals (documents/expected_blocks/
# resolution), each by name, before any study ever resolves.
# ---------------------------------------------------------------------------


def test_builder_returns_an_axis_contract_declaring_an_integer_study_value():
    axis = block_mesh_resolution_axis(
        "my_axis", documents=("system/blockMeshDict",), resolution=_isotropic,
    )
    assert isinstance(axis, AxisContract)
    assert axis.name == "my_axis"
    assert axis.value_kind == "integer"
    assert callable(axis.resolve)


def test_builder_refuses_a_bare_string_for_documents():
    with pytest.raises(TypeError, match="not a bare string"):
        block_mesh_resolution_axis(
            "my_axis", documents="system/blockMeshDict", resolution=_isotropic,
        )


def test_builder_refuses_an_empty_documents_sequence():
    with pytest.raises(ValueError, match="at least one document"):
        block_mesh_resolution_axis("my_axis", documents=(), resolution=_isotropic)


@pytest.mark.parametrize("bad_expected_blocks", [0, -1, True, "3", 1.5])
def test_builder_refuses_a_non_positive_integer_expected_blocks(bad_expected_blocks):
    with pytest.raises(ValueError, match="expected_blocks must be a positive integer"):
        block_mesh_resolution_axis(
            "my_axis", documents=("system/blockMeshDict",), resolution=_isotropic,
            expected_blocks=bad_expected_blocks,
        )


def test_builder_refuses_a_non_callable_resolution():
    with pytest.raises(TypeError, match="resolution must be callable"):
        block_mesh_resolution_axis(
            "my_axis", documents=("system/blockMeshDict",), resolution="not callable",
        )


# ---------------------------------------------------------------------------
# Happy path: one document.
# ---------------------------------------------------------------------------


def test_resolve_produces_the_planners_hex_cell_counts_patch(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
    )

    result = axis.resolve(20, case_root)

    assert isinstance(result, AxisResult)
    assert result.command_arguments == {}
    assert len(result.patches) == 1
    patch = result.patches[0]
    assert patch.document == "system/blockMeshDict"
    # expected_blocks=1 (the default) still produces the bare key path --
    # byte-for-byte the same spelling a direct `document:hex_cell_counts`
    # study key already sorts to (P2's own backward-compatibility decision).
    assert patch.key_path == ("hex_cell_counts",)
    # Typed data (2026-09-25 correction), not `plan_block_mesh_resolution`'s
    # own pre-joined text -- see the module docstring's dated correction for
    # why a `ParameterAssignment` must never carry rendered text as a value.
    assert patch.value == (20, 20, 20)
    # The writer that actually rewrites bytes reconstructs the exact string
    # `plan_block_mesh_resolution` would produce from this same tuple.
    assert plan_block_mesh_resolution(
        "system/blockMeshDict", " ".join(str(c) for c in patch.value),
    )["hex_cell_counts"] == "20 20 20"


def test_resolve_supports_a_non_isotropic_resolution_formula(tmp_path):
    """`resolution` is the record's own pure formula -- this axis does not
    assume it is always isotropic."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "cable_cells", documents=("system/blockMeshDict",),
        resolution=lambda n, current, extents=None: (n, 1, 1),
    )

    result = axis.resolve(50, case_root)

    assert result.patches[0].value == (50, 1, 1)


def test_resolution_receives_the_documents_own_current_cell_counts(tmp_path):
    """P2's own point: `resolution` sees the document's current counts, not
    only the study value -- the reusable "a direction at 1 stays 1" shape
    (owner decision (d)) is impossible without this."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    seen = []

    def resolution(value, current, extents=None):
        del extents
        seen.append(current)
        return tuple(value if c != 1 else 1 for c in current)

    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=resolution,
    )

    result = axis.resolve(20, case_root)

    # `_ONE_HEX_BLOCK_DICT`'s current resolution is (10, 1, 1): the first
    # direction is genuinely refined (10, not 1), the other two are not.
    assert seen == [(10, 1, 1)]
    assert result.patches[0].value == (20, 1, 1)


def test_several_documents_each_get_their_own_current_counts_and_own_patch(tmp_path):
    """The reason `documents` is plural at all: bathBidomain's three
    `blockMeshDict.<dim>` files each have their OWN current resolution, and
    one study value (`N`) must patch every one of them, each keeping its own
    un-refined directions at 1."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict.1D").write_text(
        "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (80 1 1) simpleGrading (1 1 1)\n);\n"
    )
    (case_root / "system" / "blockMeshDict.2D").write_text(
        "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (80 80 1) simpleGrading (1 1 1)\n);\n"
    )
    (case_root / "system" / "blockMeshDict.3D").write_text(
        "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (80 80 80) simpleGrading (1 1 1)\n);\n"
    )

    def stays_at_one(n, current, extents=None):
        del extents
        return tuple(n if c != 1 else 1 for c in current)

    axis = block_mesh_resolution_axis(
        "number_cells",
        documents=(
            "system/blockMeshDict.1D",
            "system/blockMeshDict.2D",
            "system/blockMeshDict.3D",
        ),
        resolution=stays_at_one,
    )

    result = axis.resolve(20, case_root)

    by_document = {patch.document: patch.value for patch in result.patches}
    assert by_document == {
        "system/blockMeshDict.1D": (20, 1, 1),
        "system/blockMeshDict.2D": (20, 20, 1),
        "system/blockMeshDict.3D": (20, 20, 20),
    }


# ---------------------------------------------------------------------------
# ``extents`` (added 2026-09-26, controller review of `2125168`). What a
# ``resolution`` sees of the document's own geometry is tested against the
# real native files in ``test_axes_block_mesh_resolution_native.py``.
# Corrected 2026-09-26 (review 54b M5): a test here built 20x3x7 and
# 40x6x14 mm ``blockMeshDict``s from nothing, against the owner's "testing
# against real meshes" rule; it is replaced there. The case below uses no
# geometry: it pins that a document with no ``vertices`` gives ``None``.
# ---------------------------------------------------------------------------


def test_extents_is_none_for_a_document_with_no_vertices_block(tmp_path):
    """A synthetic fixture that only ever exercises cell counts (this
    module's other tests) has no `vertices` block at all -- `extents` is
    `None`, not a refusal, so a `resolution` that never reads it (every
    other test in this module) is unaffected."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    seen = []

    def resolution(value, current, extents):
        del current
        seen.append(extents)
        return (value, value, value)

    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=resolution,
    )
    axis.resolve(20, case_root)

    assert seen == [None]


# ---------------------------------------------------------------------------
# Resolve-time refusals.
# ---------------------------------------------------------------------------


def test_resolve_refuses_a_non_integer_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",),
        resolution=lambda n, current, extents=None: (n, n, "20"),
    )

    with pytest.raises(ValueError, match="must return a tuple of 3 integers"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_boolean_masquerading_as_an_integer_count(tmp_path):
    """`bool` is an `int` subclass in Python -- `True`/`False` must still be
    refused, not silently accepted as 1/0."""
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",),
        resolution=lambda n, current, extents=None: (n, n, True),
    )

    with pytest.raises(ValueError, match="must return a tuple of 3 integers"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_non_positive_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",),
        resolution=lambda n, current, extents=None: (0, n, n),
    )

    with pytest.raises(ValueError, match="non-positive cell count"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_negative_cell_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",),
        resolution=lambda n, current, extents=None: (-5, n, n),
    )

    with pytest.raises(ValueError, match="non-positive cell count"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_document_that_does_not_exist_in_the_staged_case(tmp_path):
    case_root = tmp_path / "case"
    case_root.mkdir()
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
    )

    with pytest.raises(ValueError, match="does not exist in the staged case"):
        axis.resolve(20, case_root)


def test_resolve_refuses_when_one_of_several_documents_is_missing(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict.1D", _ONE_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells",
        documents=("system/blockMeshDict.1D", "system/blockMeshDict.2D"),
        resolution=_isotropic,
    )

    with pytest.raises(ValueError, match="system/blockMeshDict.2D"):
        axis.resolve(20, case_root)


# ---------------------------------------------------------------------------
# expected_blocks: now checked at resolve() time (P2's own behaviour change
# -- see below), and threaded through the produced patch's key path.
# ---------------------------------------------------------------------------


def test_expected_blocks_greater_than_one_is_threaded_through_the_key_path(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
        expected_blocks=2,
    )

    result = axis.resolve(20, case_root)

    assert result.patches[0].key_path == ("hex_cell_counts", "2")
    assert result.patches[0].value == (20, 20, 20)


def test_resolve_succeeds_against_a_document_with_the_correctly_declared_block_count(tmp_path):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
        expected_blocks=2,
    )

    result = axis.resolve(20, case_root)

    assert result.patches[0].value == (20, 20, 20)


def test_resolve_refuses_a_document_whose_real_block_count_disagrees_with_expected_blocks(
    tmp_path,
):
    """**Corrected 2026-09-26 (P2).** Before this axis had to read a
    document's current cell counts (to hand them to `resolution`), a
    mismatched `expected_blocks` was NOT caught here at all -- `resolve()`
    only ever checked document existence, and the real block-count check
    was deferred all the way to whichever writer eventually rendered the
    patch (see `test_the_axis_produced_value_still_refuses_the_wrong_
    block_count_when_rendered`'s OLD docstring, and this module's own
    dated correction). Now that `resolution` needs the document's own
    current counts as an input, this axis already reads the document via
    `read_hex_cell_counts` -- which performs the SAME `expected_blocks`
    check `plan_block_mesh_resolution`'s renderer always has -- so a
    record that declares the wrong `expected_blocks` for a real document is
    refused immediately, at `resolve()` time, not only when a future writer
    commits the patch.
    """
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
        expected_blocks=1,
    )

    with pytest.raises(KeyError, match="expected 1 hex"):
        axis.resolve(20, case_root)


def test_resolve_refuses_a_document_whose_blocks_disagree_with_each_other(tmp_path):
    case_root = _staged_case(
        tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT_DISAGREEING,
    )
    axis = block_mesh_resolution_axis(
        "number_cells", documents=("system/blockMeshDict",), resolution=_isotropic,
        expected_blocks=2,
    )

    with pytest.raises(KeyError, match="do not share one cell count"):
        axis.resolve(20, case_root)


# ---------------------------------------------------------------------------
# The pinning test, corrected 2026-09-26 (P2). The OLD version proved a
# mismatched real block count was refused only when a patch was actually
# RENDERED, never at `axis.resolve()` time (the axis, by design, never read
# the document at all -- only checked its existence). That is no longer
# true: `resolve()` now must read each document's current cell counts to
# hand them to `resolution`, and that read already performs the exact same
# `expected_blocks` check -- so a record declaring the wrong count is now
# refused immediately, at `resolve()` time
# (`test_resolve_refuses_a_document_whose_real_block_count_disagrees_with_
# expected_blocks`, above), not deferred to whichever writer eventually
# commits the patch.
#
# This test instead proves the RENDERER's own `expected_blocks` check
# (`plan_block_mesh_resolution`/`_rewrite_hex_block_lines`, reused by
# `render_patch_case_files`) still fires independently of the axis
# entirely: a caller can build a `plan_block_mesh_resolution` target
# directly (as `cardiacfoam.overrides._target_for_parameter` does, from
# whatever `expected_blocks` a `ParameterAssignment`'s key path carries) and
# the renderer still refuses a real document whose block count disagrees --
# the check the axis's own module docstring used to describe as "deferred
# to the renderer" is still there, just no longer the ONLY place it fires.
# ---------------------------------------------------------------------------


def test_the_renderer_still_refuses_the_wrong_expected_blocks_independently_of_the_axis(
    tmp_path,
):
    case_root = _staged_case(tmp_path, "system/blockMeshDict", _TWO_HEX_BLOCK_DICT)

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
            # A real document with two hex ( blocks, but a target declaring
            # expected_blocks=1 -- exactly the mismatch this whole task
            # fixes the WRITER/READER side of (P2); the RENDERER's own
            # check is unrelated to that fix and still catches it here.
            plan_block_mesh_resolution("system/blockMeshDict", "20 20 20", expected_blocks=1),
        ),
        preconditions=(), expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )

    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )
