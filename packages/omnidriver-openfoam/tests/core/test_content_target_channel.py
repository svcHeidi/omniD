"""`plan_verbatim_content` and `render_patch_case_files`'s `"content"`
target: a whole document's exact bytes, supplied by the caller rather than
assembled from a key/value edit. Owned by OpenFOAM and pinned here, in its
own suite, rather than only through a downstream plugin's adapter test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment, ResolvedMutation
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.case_planning import plan_verbatim_content

_TEMPLATE_TEXT = "FoamFile\n{\n}\ntype electroModel;\n"


def _delta_t_assignment(value: float) -> ParameterAssignment:
    """A real, ordinary key/value `ParameterAssignment` to combine with a
    `"content"` target; which document/key it addresses is incidental."""
    return ParameterAssignment(
        qualified_id="deltaT", owner="test", document="system/controlDict",
        key_path=("deltaT",), value=value, value_kind="scalar",
        source="case",
    )


def _request(case_root: Path) -> CaseMutationRequest:
    """A zero-parameter `clone_and_patch` request, declaring a source
    artifact instead -- a whole-template-file swap's own shape."""
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
        expected_effects=("author constant/electroProperties",),
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
        expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="authored once"):
        _render(resolved, tmp_path)


def test_a_content_target_can_author_a_document_that_does_not_exist_yet(tmp_path):
    """Unlike every other patch target, `"content"` does not require the
    document to already exist under `case_root`."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    assert not (case_root / "constant" / "electroProperties").exists()

    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),),
        expected_effects=(),
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
    """A `"content"` target relaxes the "document must already exist" rule
    only for itself: an ordinary key/value edit against a document that is
    not there must still fail loudly."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    delta_t = _delta_t_assignment(1e-4)
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
        expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="system/controlDict"):
        _render(resolved, tmp_path)


def test_a_content_target_plus_a_value_edit_on_the_same_document_lands_on_top(tmp_path):
    """A content target may author a document's whole body, and a value
    edit on that same document is applied afterward, atop the
    just-authored content -- not a second, independent write."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    control_dict_text = "FoamFile\n{\n}\ndeltaT 1e-06;\nendTime 1;\n"

    delta_t = _delta_t_assignment(2.5e-4)
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
        expected_effects=(),
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
    """A `"content"` target against a document that already exists must
    still carry a real `before_digest`/`mode`, like every other patch
    target, not the `None`/`None` a freshly authored document gets."""
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    existing_path = case_root / "constant" / "electroProperties"
    existing_path.write_text("// a previous solver variant's content\n")
    existing_path.chmod(0o644)

    resolved = ResolvedMutation(
        request=_request(case_root),
        targets=(plan_verbatim_content("constant/electroProperties", _TEMPLATE_TEXT),),
        expected_effects=(),
        semantic_owner_id="org.omnidriver.test",
    )
    rendered = _render(resolved, tmp_path)
    assert rendered[0].exists_before is True
    assert rendered[0].before_digest is not None
    assert rendered[0].mode == 0o644
    assert rendered[0].content == _TEMPLATE_TEXT.encode()
