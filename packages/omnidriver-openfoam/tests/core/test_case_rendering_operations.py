"""`ParameterAssignment.operation` reaches the renderer -- 2026-09-23
decision, "a parameter asserts a final state, not only a value"
(``docs/superpowers/plans/2026-09-23-phase3-finish-the-write-channel.md``).

``render_patch_case_files`` is the one place OpenFOAM syntax may answer what
``set``/``ensure``/``remove`` mean: ``set`` keeps the pre-existing, strict
``update_foam_entry`` behaviour (no key creation); ``ensure`` maps onto
``update_foam_entry``'s own ``add_if_missing``; ``remove`` calls
``remove_foam_entry`` instead. A ``dict_operation`` target -- not a
``ParameterAssignment`` at all, the same "not a key/value edit" reasoning
the hex-block target already has -- inserts or deletes a whole named
sub-dictionary verbatim, needed for `manufactured_bath_bidomain`'s
``ecgDomains`` block (Task 6's completion).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment, ResolvedMutation
from omnidriver.openfoam import case_rendering

_FIXTURE = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      electroProperties;
}

existingScalar 5;

bathPotentialDomain
{
    groundPatches
    {
        xMin 0;
    }
}
"""


def _case(tmp_path: Path) -> Path:
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "electroProperties").write_text(_FIXTURE)
    return case_root


def _assignment(*, key_path, value, value_kind="scalar", operation="set") -> ParameterAssignment:
    return ParameterAssignment(
        qualified_id=".".join(key_path), owner="test",
        document="constant/electroProperties", key_path=key_path, binding={},
        value=value, value_kind=value_kind, source="case", operation=operation,
    )


def _resolved(case_root: Path, *parameters: ParameterAssignment, extra_targets=()) -> ResolvedMutation:
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(), parameters=parameters, requested_by="test",
    )
    targets = tuple(
        {
            "document": p.document,
            "expanded_key_path": list(p.expanded_key_path()),
            "operation": p.operation,
            "format": "openfoam_dictionary",
            **({"value": p.value} if p.operation != "remove" else {}),
        }
        for p in parameters
    ) + tuple(extra_targets)
    return ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )


def _render(resolved, tmp_path):
    rendered = case_rendering.render_patch_case_files(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=None,
        execution_env=None, renderer_id="test",
    )
    return next(f for f in rendered if f.path == "constant/electroProperties").content.decode()


def test_set_on_an_existing_key_still_writes(tmp_path):
    case_root = _case(tmp_path)
    parameter = _assignment(key_path=("existingScalar",), value=9, operation="set")
    content = _render(_resolved(case_root, parameter), tmp_path)
    assert "existingScalar    9;" in content


def test_set_on_a_missing_key_now_raises(tmp_path):
    """Corrected 2026-09-23: before this, every channel-routed edit was
    applied with ``add_if_missing=True`` regardless of what it asserted,
    silently more permissive than the direct writer it replaces
    (``apply_entry_overrides``, which has never allowed a missing key for a
    plain ``set``)."""
    case_root = _case(tmp_path)
    parameter = _assignment(key_path=("noSuchKey",), value=9, operation="set")
    with pytest.raises(KeyError, match="noSuchKey"):
        _render(_resolved(case_root, parameter), tmp_path)


def test_ensure_creates_a_missing_key(tmp_path):
    case_root = _case(tmp_path)
    parameter = _assignment(
        key_path=("bathPotentialDomain", "groundPatches", "xMax"),
        value=1.5, operation="ensure",
    )
    content = _render(_resolved(case_root, parameter), tmp_path)
    assert "xMax    1.5;" in content
    # The pre-existing sibling is untouched.
    assert "xMin 0;" in content


def test_ensure_on_an_existing_key_overwrites_it(tmp_path):
    case_root = _case(tmp_path)
    parameter = _assignment(key_path=("existingScalar",), value=42, operation="ensure")
    content = _render(_resolved(case_root, parameter), tmp_path)
    assert "existingScalar    42;" in content


def test_remove_deletes_an_existing_key(tmp_path):
    case_root = _case(tmp_path)
    parameter = _assignment(
        key_path=("bathPotentialDomain", "groundPatches", "xMin"),
        value=None, operation="remove",
    )
    content = _render(_resolved(case_root, parameter), tmp_path)
    assert "xMin" not in content


def test_remove_of_an_already_absent_key_is_a_no_op(tmp_path):
    """`remove` asserts the document's final state -- the key is gone -- not
    that a deletion action occurred. A key already absent already satisfies
    that assertion, so this must not raise."""
    case_root = _case(tmp_path)
    parameter = _assignment(
        key_path=("bathPotentialDomain", "groundPatches", "neverExisted"),
        value=None, operation="remove",
    )
    content = _render(_resolved(case_root, parameter), tmp_path)
    assert "xMin 0;" in content  # untouched


def test_an_unknown_operation_on_a_target_is_refused_by_name(tmp_path):
    case_root = _case(tmp_path)
    parameter = _assignment(key_path=("existingScalar",), value=9)
    resolved = _resolved(case_root, parameter)
    # Corrupt the target's operation directly -- a real resolver only ever
    # emits `set`/`ensure`/`remove` (`ParameterAssignment` itself refuses
    # any other name), so this exercises the renderer's own defensive check
    # against a malformed target from a future or misbehaving resolver.
    bad_target = dict(resolved.targets[0])
    bad_target["operation"] = "banana"
    resolved = ResolvedMutation(
        request=resolved.request, targets=(bad_target,), preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )
    with pytest.raises(ValueError, match="banana"):
        _render(resolved, tmp_path)


def test_a_target_with_no_operation_key_defaults_to_set(tmp_path):
    """A target built before this field existed (no `"operation"` key at
    all, the shape every pre-2026-09-23 caller still produces) must behave
    exactly as `set` always has."""
    case_root = _case(tmp_path)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.omnidriver.test",
        workflow="test", source_artifacts=(),
        parameters=(_assignment(key_path=("existingScalar",), value=9),),
        requested_by="test",
    )
    targets = (
        {
            "document": "constant/electroProperties",
            "expanded_key_path": ["existingScalar"],
            "value": 9,
            "format": "openfoam_dictionary",
        },
    )
    resolved = ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=(), semantic_owner_id="org.omnidriver.test",
    )
    content = _render(resolved, tmp_path)
    assert "existingScalar    9;" in content


# --- dict_operation: a whole sub-dictionary inserted/removed verbatim, not
# a ParameterAssignment (see this module's docstring). ---

_ECG_BLOCK = """    ecgDomains
    {
        bodyECG
        {
            ecgSolver torsoECG;
        }
    }

"""


def test_dict_operation_ensure_inserts_a_whole_block(tmp_path):
    case_root = _case(tmp_path)
    target = {
        "document": "constant/electroProperties",
        "dict_operation": "ensure",
        "dict_name": "ecgDomains",
        "block_text": _ECG_BLOCK,
        "scope": None,
        "format": "openfoam_dictionary",
    }
    # `CaseMutationRequest` still requires >=1 real `ParameterAssignment` for
    # `clone_and_patch` -- paired with an unrelated real edit, the same
    # `extra_targets` shape `commit_case_overrides` uses in production.
    parameter = _assignment(key_path=("existingScalar",), value=5, operation="set")
    resolved = _resolved(case_root, parameter, extra_targets=(target,))
    content = _render(resolved, tmp_path)
    assert "ecgDomains" in content
    assert "torsoECG" in content


def test_dict_operation_ensure_then_set_inside_the_new_block_in_one_commit(tmp_path):
    """The real bath-bidomain ordering: the block must exist before a scoped
    `set` inside it can find its key at all -- `render_patch_case_files`
    applies `dict_operation` targets before ordinary value edits precisely
    so this works in one commit."""
    case_root = _case(tmp_path)
    dict_target = {
        "document": "constant/electroProperties",
        "dict_operation": "ensure",
        "dict_name": "ecgDomains",
        "block_text": _ECG_BLOCK,
        "scope": None,
        "format": "openfoam_dictionary",
    }
    set_inside_block = _assignment(
        key_path=("ecgDomains", "bodyECG", "ecgSolver"), value="pseudoECG",
        value_kind="word", operation="set",
    )
    resolved = _resolved(case_root, set_inside_block, extra_targets=(dict_target,))
    content = _render(resolved, tmp_path)
    assert "pseudoECG" in content
    assert "torsoECG" not in content


def test_dict_operation_remove_deletes_a_whole_block(tmp_path):
    case_root = _case(tmp_path)
    # First give the fixture a block to remove.
    electro = case_root / "constant" / "electroProperties"
    electro.write_text(electro.read_text() + "\n" + _ECG_BLOCK)
    target = {
        "document": "constant/electroProperties",
        "dict_operation": "remove",
        "dict_name": "ecgDomains",
        "scope": None,
        "format": "openfoam_dictionary",
    }
    parameter = _assignment(key_path=("existingScalar",), value=5, operation="set")
    resolved = _resolved(case_root, parameter, extra_targets=(target,))
    content = _render(resolved, tmp_path)
    assert "ecgDomains" not in content


def test_dict_operation_remove_of_an_already_absent_block_is_a_no_op(tmp_path):
    case_root = _case(tmp_path)
    target = {
        "document": "constant/electroProperties",
        "dict_operation": "remove",
        "dict_name": "neverExisted",
        "scope": None,
        "format": "openfoam_dictionary",
    }
    parameter = _assignment(key_path=("existingScalar",), value=5, operation="set")
    resolved = _resolved(case_root, parameter, extra_targets=(target,))
    content = _render(resolved, tmp_path)
    assert "existingScalar    5;" in content


def test_dict_operation_unknown_kind_is_refused(tmp_path):
    case_root = _case(tmp_path)
    target = {
        "document": "constant/electroProperties",
        "dict_operation": "banana",
        "dict_name": "ecgDomains",
        "scope": None,
        "format": "openfoam_dictionary",
    }
    parameter = _assignment(key_path=("existingScalar",), value=5, operation="set")
    resolved = _resolved(case_root, parameter, extra_targets=(target,))
    with pytest.raises(ValueError, match="banana"):
        _render(resolved, tmp_path)
