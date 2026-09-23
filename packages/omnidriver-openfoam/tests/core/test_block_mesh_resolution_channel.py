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
from omnidriver.openfoam.utils import (
    plan_block_mesh_resolution,
    plan_delta_t,
    replace_block_mesh_resolutions,
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
# Characterization: the direct writer against the real fixture, captured
# before Task 4's change and asserted unchanged after.
# --------------------------------------------------------------------------


def test_characterizes_the_direct_writer_against_the_real_fixture(tmp_path):
    path = tmp_path / "blockMeshDict"
    path.write_text(REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D)
    replace_block_mesh_resolutions(path, "40 40 40", expected_blocks=3)
    text = path.read_text()
    expected = REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D.replace(
        "(80 80 80) simpleGrading", "(40 40 40) simpleGrading",
    )
    assert text == expected
    assert text.count("(40 40 40) simpleGrading") == 3


def test_wrong_expected_blocks_still_refuses_against_the_real_fixture(tmp_path):
    """`expected_blocks` is the whole reason this function exists -- silently
    replacing the wrong number of blocks is the failure it prevents. Proven
    against real content with a genuine multi-block count, not a
    single-block fixture that could not distinguish 1 from "the wrong
    number"."""
    path = tmp_path / "blockMeshDict"
    path.write_text(REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D)
    with pytest.raises(KeyError, match="Expected to update 1 hex blocks"):
        replace_block_mesh_resolutions(path, "40 40 40", expected_blocks=1)
    # Corrected 2026-09-23 (Phase 3 Task 4): the file is left untouched on a
    # mismatch (see `replace_block_mesh_resolutions`'s docstring) -- the
    # pre-Task-4 version would have already overwritten it with the
    # (wrong-count) rewrite by the time this raised.
    assert path.read_text() == REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D


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


def test_the_renderer_is_byte_identical_to_the_direct_writer(tmp_path):
    """The migration proof: the same real content, the same requested
    resolution, through both paths, must produce the same bytes."""
    case_root = _real_case(tmp_path)
    resolved = _resolved_for(case_root)
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )
    via_renderer = next(f for f in rendered if f.path == "system/blockMeshDict").content

    direct_path = tmp_path / "direct" / "blockMeshDict"
    direct_path.parent.mkdir()
    direct_path.write_text(REAL_BATH_BIDOMAIN_BLOCK_MESH_DICT_3D)
    replace_block_mesh_resolutions(direct_path, "40 40 40", expected_blocks=3)
    via_direct_writer = direct_path.read_bytes()

    assert via_renderer == via_direct_writer
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
