"""`replace_block_mesh_resolutions` joins the resolve/render channel as a
structural patch target -- Phase 3 Task 4
(``docs/superpowers/plans/2026-09-23-phase3-finish-the-write-channel.md``).

Characterized against a **real** `blockMeshDict`, not an invented fixture
(this repository's own "no invented-geometry tests" rule): the three
``hex (`` blocks below are transcribed byte-for-byte from
``tutorials/manufacturedSolutions/bathBidomain/system/blockMeshDict.3D`` in
the authoritative native tree,
``~/noFrontendCardiacFoam_minor_errors`` -- sha256
``9227c596bc633226c480060f1a9bdd85fe87302e2ff94b23074b91e2e98906a8`` over the
constant below (checked by
`test_the_embedded_fixture_matches_its_cited_digest`), recomputable from that
file. Embedded rather than read from
that path at test time (unlike
``test_the_include_closure_is_exercised_against_the_native_install``'s real
OpenFOAM install check) because a `blockMeshDict` is a tutorial asset, not
something this repository or a real OpenFOAM install ships -- there is
nothing to `pytest.skip` against on a machine without that tree checked out.

This same real file is why Task 4's Step 1 finding goes further than the
plan's own framing: the plan asked to check `manufactured_monodomain_1d3d`
for whether it patches a document the framework did not author. It does --
but so does every one of the other seven `replace_block_mesh_resolutions`
callers. This fixture proves it: three ``hex (`` blocks with tutorial-authored
vertex indices and an ``xMin``/``xMax``/``sides`` boundary, nothing like
`mesh_provisioning.default_block_mesh_dict_text`'s generic one-block slab
with a single ``walls`` patch. A whole-document render candidate cannot
reproduce this content from any synthesis this framework owns; only a
format-owned patch target (candidate 2) can.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment, ResolvedMutation
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.case_planning import (
    _rewrite_hex_block_lines,
    plan_block_mesh_resolution,
    plan_delta_t,
)

# Transcribed byte-for-byte from the authoritative native tree (see module
# docstring). Three `hex (` blocks, each `(80 80 80)`, matching this
# tutorial's real `replace_block_mesh_resolutions(..., expected_blocks=3)`
# call (manufactured_bath_bidomain.py:317).
REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D = """\
/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v1912                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}

vertices
(
    (-1 0 0) (0 0 0) (1 0 0) (2 0 0)
    (-1 1 0) (0 1 0) (1 1 0) (2 1 0)
    (-1 0 1) (0 0 1) (1 0 1) (2 0 1)
    (-1 1 1) (0 1 1) (1 1 1) (2 1 1)
);

blocks
(
    hex (0 1 5 4 8 9 13 12) (80 80 80) simpleGrading (1 1 1)
    hex (1 2 6 5 9 10 14 13) (80 80 80) simpleGrading (1 1 1)
    hex (2 3 7 6 10 11 15 14) (80 80 80) simpleGrading (1 1 1)
);

boundary
(
    xMin
    {
        type patch;
        faces ((0 8 12 4));
    }
    xMax
    {
        type patch;
        faces ((3 7 15 11));
    }
    sides
    {
        type patch;
        faces
        (
            (0 1 9 8)
            (1 2 10 9)
            (2 3 11 10)
            (4 12 13 5)
            (5 13 14 6)
            (6 14 15 7)
            (0 4 5 1)
            (1 5 6 2)
            (2 6 7 3)
            (8 9 13 12)
            (9 10 14 13)
            (10 11 15 14)
        );
    }
);

mergePatchPairs
(
);

// ************************************************************************* //
"""


def test_the_embedded_fixture_matches_its_cited_digest():
    """A transcription error would silently invalidate every test below;
    check it against the digest the module docstring cites, computed
    independently from the native tree file at authoring time."""
    digest = hashlib.sha256(REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D.encode()).hexdigest()
    assert digest == "9227c596bc633226c480060f1a9bdd85fe87302e2ff94b23074b91e2e98906a8"


# --------------------------------------------------------------------------
# Step 1 evidence: real content, not `default_block_mesh_dict_text`-shaped.
# --------------------------------------------------------------------------


def test_real_content_is_not_reproducible_by_the_generic_synthesis_template():
    from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text

    generic = default_block_mesh_dict_text()
    assert generic.count("hex (") == 1  # the real fixture has three
    assert "xMin" not in generic  # the real fixture's boundary; generic has "walls" only
    assert "walls" not in REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D


# --------------------------------------------------------------------------
# Characterization: `_rewrite_hex_block_lines` against the real fixture.
#
# **Corrected 2026-09-23 (Phase 3 Task 6's completion).** These two tests
# used to drive `replace_block_mesh_resolutions` -- the direct writer this
# module characterized before Task 4's change. That writer is now retired
# (Task 6 migrated its last caller, `grep -rn
# "replace_block_mesh_resolutions(" packages/*/src/` returns zero), so these
# drive `_rewrite_hex_block_lines` directly instead -- the shared pure
# grammar both the retired writer and `render_patch_case_files` always
# called; the writer added only a file read/write around it. Same fixture,
# same assertions: the behaviour these tests pin has not moved, only the
# entry point has. (`test_common_blockmesh_resize.py`, the direct writer's
# OWN dedicated unit tests, is deleted in the same commit as the writer --
# its four cases were the 3D/1D replace and the missing-file/missing-hex-line
# raises; the replace and wrong-count-raise behaviour survive here and in
# `test_the_renderer_still_refuses_the_wrong_expected_blocks` below, the 1D
# case gets its own test just below, and "missing file" has no successor
# because nothing in this codebase takes a bare block-mesh path any more --
# `render_patch_case_files` checks document existence against a case root,
# a different, already-covered shape of check.)
# --------------------------------------------------------------------------


def test_rewrite_hex_block_lines_against_the_real_fixture(tmp_path):
    text = _rewrite_hex_block_lines(
        REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D, "40 40 40", 3, label="blockMeshDict",
    )
    expected = REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D.replace(
        "(80 80 80) simpleGrading", "(40 40 40) simpleGrading",
    )
    assert text == expected
    assert text.count("(40 40 40) simpleGrading") == 3


def test_rewrite_hex_block_lines_against_a_1d_single_block_fixture():
    """The other real shape every migrated tutorial's block mesh actually
    has: a single `hex (` line, not three. Closes the gap
    `test_common_blockmesh_resize.py`'s own `test_replaces_single_hex_block_for_1d`
    used to cover for the now-retired direct writer -- same cell-counts
    string shape (`"50 1 1"`, a 1D cable), same one-block fixture shape
    every 1D tutorial's real `blockMeshDict` has (see e.g.
    `test_cable_1d_restitution_write_channel.py`'s own fixture)."""
    text = _rewrite_hex_block_lines(
        "FoamFile\n{\n    object blockMeshDict;\n}\n"
        "blocks\n(\n"
        "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
        ");\n",
        "50 1 1", 1, label="blockMeshDict",
    )
    assert "hex (0 1 2 3 4 5 6 7) (50 1 1) simpleGrading (1 1 1)" in text


def test_wrong_expected_blocks_still_refuses_against_the_real_fixture(tmp_path):
    """`expected_blocks` is the whole reason this function exists -- silently
    replacing the wrong number of blocks is the failure it prevents. Proven
    against real content with a genuine multi-block count, not a
    single-block fixture that could not distinguish 1 from "the wrong
    number"."""
    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        _rewrite_hex_block_lines(
            REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D, "40 40 40", 1, label="blockMeshDict",
        )


# --------------------------------------------------------------------------
# The new path: `plan_block_mesh_resolution` (pure) + the patch renderer
# (reads the real case, rewrites, validates `expected_blocks`).
# --------------------------------------------------------------------------


def test_the_resolver_is_pure_and_shapes_a_target_case_rendering_understands():
    target = plan_block_mesh_resolution("system/blockMeshDict", "40 40 40", expected_blocks=3)
    assert target == {
        "document": "system/blockMeshDict",
        "format": case_rendering.FORMAT,
        "hex_cell_counts": "40 40 40",
        "expected_blocks": 3,
    }


def test_the_resolver_refuses_a_cell_count_string_carrying_a_directive():
    # Reused, not re-implemented: `mutators._format_value`'s existing
    # `;`/`#`/newline security refusal (SECURITY.md), which
    # `replace_block_mesh_resolutions` itself never applied.
    with pytest.raises(ValueError, match="directive"):
        plan_block_mesh_resolution("system/blockMeshDict", "40 40 40 #include x", expected_blocks=3)


def _resolved_for(case_root: Path) -> ResolvedMutation:
    """A `ResolvedMutation` combining a real-shaped `ParameterAssignment`
    edit (`controlDict.deltaT`, Task 3's own `plan_delta_t`) with the new
    hex-block target -- exactly the shape a real tutorial resolution has
    (every one of the eight `replace_block_mesh_resolutions` callers also
    edits `controlDict` in the same case). Built directly rather than
    through a plugin's `resolve_case_mutation`: no plugin resolves a
    `clone_and_patch` request combining these two document kinds yet --
    that migration is Task 6's, not this one's. `CaseMutationRequest`
    requires at least one real `ParameterAssignment` for `clone_and_patch`
    (R2 finding 7) -- there is no other field on the request a hex-only
    resolution could use to satisfy it, which is exactly why this fixture
    pairs it with a real edit rather than trying to construct a
    zero-parameter request.
    """
    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    targets = (
        {
            "document": delta_t.document,
            "expanded_key_path": list(delta_t.expanded_key_path()),
            "value": delta_t.value,
            "format": "openfoam_dictionary",
        },
        plan_block_mesh_resolution("system/blockMeshDict", "40 40 40", expected_blocks=3),
    )
    return ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=("resize blockMeshDict", "set deltaT"),
        semantic_owner_id="org.omnidriver.test",
    )


def _real_case(tmp_path: Path) -> Path:
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "blockMeshDict").write_text(REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D)
    (case_root / "system" / "controlDict").write_text(
        "FoamFile\n{\n}\ndeltaT 1e-05;\nendTime 1;\n"
    )
    return case_root


def test_the_renderer_produces_a_file_per_document_including_the_hex_patch(tmp_path):
    case_root = _real_case(tmp_path)
    resolved = _resolved_for(case_root)
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )
    by_path = {file.path: file for file in rendered}
    assert set(by_path) == {"system/blockMeshDict", "system/controlDict"}
    assert by_path["system/controlDict"].content.decode().count("deltaT") == 1
    assert b"0.0001" in by_path["system/controlDict"].content


def test_the_renderer_is_byte_identical_to_rewrite_hex_block_lines(tmp_path):
    """The migration proof, Task 4's own framing, updated 2026-09-23 (Task
    6's completion) now that the once-independent direct writer is retired:
    the renderer must still produce exactly what `_rewrite_hex_block_lines`
    -- the shared grammar both used, and the only one of the two still
    standing -- computes directly over the same real content and the same
    requested resolution."""
    case_root = _real_case(tmp_path)
    resolved = _resolved_for(case_root)
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )
    via_renderer = next(f for f in rendered if f.path == "system/blockMeshDict").content

    via_direct_call = _rewrite_hex_block_lines(
        REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D, "40 40 40", 3, label="blockMeshDict",
    ).encode()

    assert via_renderer == via_direct_call
    assert via_renderer.count(b"(40 40 40) simpleGrading") == 3


def test_the_renderer_still_refuses_the_wrong_expected_blocks(tmp_path):
    case_root = _real_case(tmp_path)
    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    targets = (
        {
            "document": delta_t.document,
            "expanded_key_path": list(delta_t.expanded_key_path()),
            "value": delta_t.value,
            "format": "openfoam_dictionary",
        },
        plan_block_mesh_resolution("system/blockMeshDict", "40 40 40", expected_blocks=1),
    )
    resolved = ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )


def test_the_renderer_refuses_a_missing_block_mesh_dict(tmp_path):
    """A missing `blockMeshDict` fails loudly, naming the document.

    Added 2026-09-23. The retired `replace_block_mesh_resolutions` pinned this
    with `test_missing_file_raises` (`FileNotFoundError`), in
    `tests/core/test_common_blockmesh_resize.py`, which Phase 3 Task 6b deleted
    along with the function. Three of that file's four behaviours have
    successors here; this one moved to the renderer -- which refuses with a
    `ValueError` naming the patch target -- but its test did not move with it.
    A structural patch against a document that is not there must never
    render silently.
    """
    case_root = _real_case(tmp_path)
    (case_root / "system" / "blockMeshDict").unlink()
    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    targets = (
        {
            "document": delta_t.document,
            "expanded_key_path": list(delta_t.expanded_key_path()),
            "value": delta_t.value,
            "format": "openfoam_dictionary",
        },
        plan_block_mesh_resolution("system/blockMeshDict", "40 40 40", expected_blocks=1),
    )
    resolved = ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="system/blockMeshDict"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )


def test_two_hex_targets_on_one_document_are_refused_as_ambiguous(tmp_path):
    case_root = _real_case(tmp_path)
    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    targets = (
        plan_block_mesh_resolution("system/blockMeshDict", "40 40 40", expected_blocks=3),
        plan_block_mesh_resolution("system/blockMeshDict", "20 20 20", expected_blocks=3),
    )
    resolved = ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="rewritten once"):
        case_rendering.render_patch_case_files(
            resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
            execution_env=None, renderer_id="test",
        )
