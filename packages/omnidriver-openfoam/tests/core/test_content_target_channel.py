"""`plan_verbatim_content` and `render_patch_case_files`'s `"content"` target
join the resolve/render channel -- Phase 3 Task 7
(``docs/superpowers/plans/2026-09-23-phase3-finish-the-write-channel.md``).

This format behaviour (a whole document's exact bytes, supplied by the
caller rather than assembled from a key/value edit) is owned by OpenFOAM, the
same way Task 4's ``hex (`` rewrite is -- so it is pinned here, in
``omnidriver-openfoam``'s own suite, not only through
``heart_solver_comparison``'s cardiacFoam-side characterization test
(``test_heart_solver_comparison_write_channel.py``). Before this file, the
`"content"` branch in `render_patch_case_files` had exactly one exerciser;
changing or removing that one adapter test would have left the renderer
itself untested.

Mirrors `test_block_mesh_resolution_channel.py`'s own structure and fixture
conventions (a real `CaseMutationRequest`/`ResolvedMutation` pair, built
directly rather than through a plugin's resolver, since no plugin's own
resolver builds a raw ``"content"`` target and a real edit in one request
yet).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ResolvedMutation
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.utils import plan_delta_t, plan_verbatim_content

_TEMPLATE_TEXT = "FoamFile\n{\n}\ntype electroModel;\n"


def _request(case_root: Path) -> CaseMutationRequest:
    """A zero-parameter `clone_and_patch` request, declaring a source
    artifact instead -- `heart_solver_comparison`'s own shape, and the real
    reason `CaseMutationRequest`'s "clone_and_patch needs a parameter"
    invariant was widened (2026-09-23, Phase 3 Task 7) to accept a source
    artifact in its place.
    """
    return CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=("test.template:electroModel",),
        parameters=(), requested_by="test",
    )


def _render(resolved: ResolvedMutation, tmp_path: Path):
    return case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )


def test_the_resolver_is_pure_and_shapes_a_target_case_rendering_understands():
    target = plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT)
    assert target == {
        "document": "constant/electroProperties",
        "format": case_rendering.FORMAT,
        "content": _TEMPLATE_TEXT,
    }


def test_a_content_target_renders_exactly_the_given_bytes(tmp_path):
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),),
        preconditions=(), expected_effects=("author constant/electroProperties",),
        semantic_owner_id="org.omnidriver.test",
    )
    rendered = _render(resolved, tmp_path)
    assert len(rendered) == 1
    assert rendered[0].path == "constant/electroProperties"
    assert rendered[0].content == _TEMPLATE_TEXT.encode()


def test_two_content_targets_on_one_document_are_refused(tmp_path):
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(
            plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),
            plan_verbatim_content("constant/electroProperties", "different text\n"),
        ),
        preconditions=(), expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="authored once"):
        _render(resolved, tmp_path)


def test_a_content_target_can_author_a_document_that_does_not_exist_yet(tmp_path):
    """Unlike every other patch target, `"content"` does not require the
    document to already exist under `case_root` -- `heart_solver_comparison`
    reuses one `case_root` across all four solver variants, and the very
    first `apply_case` call has nothing at `constant/electroProperties` yet."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    assert not (case_root / "constant" / "electroProperties").exists()

    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),),
        preconditions=(), expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    rendered = _render(resolved, tmp_path)
    assert rendered[0].content == _TEMPLATE_TEXT.encode()
    assert rendered[0].exists_before is False
    assert rendered[0].before_digest is None
    assert rendered[0].mode is None
    # The real case is never written to directly -- only the snapshot is.
    assert not (case_root / "constant" / "electroProperties").exists()


def test_a_non_content_patch_against_a_missing_document_is_still_refused(tmp_path):
    """The other half of the previous test's distinction: a `"content"`
    target relaxes the "document must already exist" rule *only* for
    itself. An ordinary key/value edit against a document that is not there
    must still fail loudly -- unchanged from before this task, and already
    pinned by `test_block_mesh_resolution_channel.py`'s own
    `test_the_renderer_refuses_a_missing_block_mesh_dict` for the hex-target
    case; this is the same guarantee for the ordinary value-edit case,
    confirmed here rather than assumed."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    delta_t = plan_delta_t(1e-4, owner="test")
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=(delta_t,), requested_by="test",
    )
    resolved = ResolvedMutation(
        request=request,
        targets=(
            {
                "document": delta_t.document,
                "expanded_key_path": list(delta_t.expanded_key_path()),
                "value": delta_t.value,
                "format": case_rendering.FORMAT,
            },
        ),
        preconditions=(), expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="system/controlDict"):
        _render(resolved, tmp_path)


def test_a_content_target_plus_a_value_edit_on_the_same_document_lands_on_top(tmp_path):
    """Mirrors `render_synthesis_case_files`'s own combination case
    (`repeated_edits_to_one_file`): a content target may author a document's
    whole body, and a value edit on that same document is applied afterward,
    atop the just-authored content -- not a second, independent write."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    control_dict_text = "FoamFile\n{\n}\ndeltaT 1e-06;\nendTime 1;\n"

    delta_t = plan_delta_t(2.5e-4, owner="test")
    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(
            plan_verbatim_content("system/controlDict", control_dict_text),
            {
                "document": delta_t.document,
                "expanded_key_path": list(delta_t.expanded_key_path()),
                "value": delta_t.value,
                "format": case_rendering.FORMAT,
            },
        ),
        preconditions=(), expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    rendered = _render(resolved, tmp_path)
    assert len(rendered) == 1
    content = rendered[0].content.decode()
    assert content.count("deltaT") == 1
    assert "0.00025" in content
    assert "endTime 1;" in content
    # The document did not exist before this render -- confirms the edit
    # really did land on the content target's own freshly authored body,
    # not on some other pre-existing file.
    assert rendered[0].exists_before is False


def test_before_digest_and_mode_are_preserved_when_the_document_already_existed(tmp_path):
    """A `"content"` target against a document that *does* already exist
    (e.g. re-running `heart_solver_comparison` for a second solver variant
    against the same reused `case_root`) must still carry a real
    `before_digest`/`mode` for the commit's own conflict check and journal --
    exactly like every other patch target, not the `None`/`None` a freshly
    authored document gets."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    existing_path = case_root / "constant" / "electroProperties"
    existing_path.write_text("// a previous solver variant's content\n")
    existing_path.chmod(0o644)

    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),),
        preconditions=(), expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    rendered = _render(resolved, tmp_path)
    assert rendered[0].exists_before is True
    assert rendered[0].before_digest is not None
    assert rendered[0].mode == 0o644
    assert rendered[0].content == _TEMPLATE_TEXT.encode()
