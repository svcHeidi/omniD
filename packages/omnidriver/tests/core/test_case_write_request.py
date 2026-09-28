"""A mutation request names its mode, its owner, and its sources.

Two creation modes, deliberately not collapsed: ``clone_and_patch`` edits an
existing case (source: that case); ``synthesize`` builds one from a catalog
and needs explicit source artifacts (a mesh, a template tree).
"""

from pathlib import Path

import pytest

from omnidriver.core import case_write


def _assignment(**overrides):
    fields = dict(
        qualified_id="$CARDIAC_CONDUCTIVITY.df",
        owner="org.cardiaccore",
        document="system/setCardiacConductivityDict",
        key_path=("df",),
        binding={},
        value=0.1,
        value_kind="scalar",
        source="case",
    )
    fields.update(overrides)
    return case_write.ParameterAssignment(**fields)


def test_an_unsupported_mode_is_refused_by_name():
    with pytest.raises(ValueError, match="rewrite"):
        case_write.CaseMutationRequest(
            mode="rewrite", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(), requested_by="test",
        )


def test_generated_input_is_no_longer_a_supported_mode():
    with pytest.raises(ValueError, match="generated_input"):
        case_write.CaseMutationRequest(
            mode="generated_input", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_assignment(),), requested_by="test",
        )


def test_synthesis_without_a_source_artifact_is_refused():
    """A case built from nothing is not a supported creation mode."""
    with pytest.raises(ValueError, match="source artifact"):
        case_write.CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_assignment(),), requested_by="test",
        )


def test_a_patch_needs_no_source_artifact():
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.a", workflow="w", source_artifacts=(),
        parameters=(_assignment(),), requested_by="test",
    )
    assert request.mode == "clone_and_patch"


def test_a_parameter_keeps_its_document_scope():
    """Two documents declaring one leaf name are two parameters.

    The unqualified form is what let an absent scar dictionary overwrite a
    present conductivity dictionary's field name (audit finding S3).
    """
    conductivity = _assignment(qualified_id="$CARDIAC_CONDUCTIVITY.fiberField",
                               document="system/setCardiacConductivityDict")
    scar = _assignment(qualified_id="$CARDIAC_SCAR.fiberField",
                       document="system/setCardiacScarDict")
    assert conductivity.slot() != scar.slot()


def test_two_assignments_to_one_slot_are_refused():
    duplicate = (_assignment(), _assignment(value=0.2))
    with pytest.raises(ValueError, match="assigned twice"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=duplicate, requested_by="test",
        )


def test_an_unknown_value_source_is_refused():
    """A value's origin is evidence. "I do not know where this came from" is
    not one of the five sources."""
    with pytest.raises(ValueError, match="plausible"):
        _assignment(source="plausible")


@pytest.mark.parametrize("source", sorted(case_write.VALUE_SOURCES))
def test_every_declared_source_is_accepted(source):
    assert _assignment(source=source).source == source


def test_an_absolute_document_path_is_refused():
    with pytest.raises(ValueError, match="case-relative"):
        _assignment(document="/etc/passwd")


def test_a_document_path_escaping_the_case_is_refused():
    with pytest.raises(ValueError, match="escape"):
        _assignment(document="../outside/dict")


def test_a_dynamic_binding_must_be_declared_not_inferred():
    """`<ventKey>` accepted `banana` because the segment was substituted
    without being checked (audit finding S1). A binding carries its allowed
    values with it."""
    with pytest.raises(ValueError, match="banana"):
        _assignment(
            qualified_id="$PURKINJE_TREE.<ventKey>.seed",
            key_path=("<ventKey>", "seed"),
            binding={"<ventKey>": "banana"},
            value=[1.0, 2.0, 3.0],
            value_kind="vector3",
            allowed_bindings={"<ventKey>": ("lv", "rv")},
        )


def test_a_declared_binding_is_accepted_and_expanded():
    assignment = _assignment(
        qualified_id="$PURKINJE_TREE.<ventKey>.seed",
        key_path=("<ventKey>", "seed"),
        binding={"<ventKey>": "lv"},
        value=[1.0, 2.0, 3.0],
        value_kind="vector3",
        allowed_bindings={"<ventKey>": ("lv", "rv")},
    )
    assert assignment.expanded_key_path() == ("lv", "seed")


# --- R2 finding 4, closed per the plan's 2026-09-23 decision section: "a
# parameter value is typed data, never rendered text". `validate_value_shape`
# was never called from `ParameterAssignment`, so the closed value_kind
# vocabulary was closed for DictEntry and wide open here -- the exact hole
# audit finding S1 was supposed to have closed. ---


def test_nan_is_refused_for_a_scalar():
    with pytest.raises(ValueError, match="finite"):
        _assignment(value=float("nan"), value_kind="scalar")


def test_an_unknown_value_kind_is_refused():
    with pytest.raises(ValueError, match="banana"):
        _assignment(value="x", value_kind="banana")


def test_a_value_not_matching_its_declared_kind_is_refused():
    with pytest.raises(ValueError, match="ionicModel"):
        _assignment(
            qualified_id="$ELECTRO.ionicModel", value=1.0, value_kind="word",
        )


# Each mode's stated prerequisite is enforced, not merely documented:
# `clone_and_patch` needs at least a parameter or a source artifact (a patch
# that names neither is a no-op masquerading as a mutation); `synthesize`
# needs a non-empty, non-whitespace source_artifacts.


def test_a_patch_with_no_parameters_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(), requested_by="test",
        )


def test_a_clone_and_patch_request_with_no_parameters_but_a_source_artifact_is_accepted():
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.a", workflow="w",
        source_artifacts=("example.solverVariants:eikonal",),
        parameters=(), requested_by="test",
    )
    assert request.parameters == ()
    assert request.source_artifacts == ("example.solverVariants:eikonal",)


def test_an_empty_source_artifact_is_refused():
    """`source_artifacts=("",)` satisfied the non-empty-tuple guard while
    naming nothing."""
    with pytest.raises(ValueError, match="non-empty"):
        case_write.CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=("",),
            parameters=(_assignment(),), requested_by="test",
        )


def test_a_whitespace_only_source_artifact_is_refused():
    with pytest.raises(ValueError, match="non-empty"):
        case_write.CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=("   ",),
            parameters=(_assignment(),), requested_by="test",
        )


# --- R3 blocker 2 (2026-09-23): a relative `case_root` resolves against
# whatever directory the *committing* process happens to be in, not the one
# the plan was built in. Reproduced against the real public constructor, not
# a monkeypatch: `commit_case_write` had no defensive check of its own, so
# the same plan committed from two different working directories silently
# wrote the right bytes into two different, wrong-relative-to-each-other
# case roots with no error at all. Refusing it here, at construction, means
# a plan naming an unauditable root never comes into existence. ---


def test_a_relative_case_root_is_refused_at_construction():
    with pytest.raises(ValueError, match="absolute"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("somecase"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_assignment(),), requested_by="test",
        )


def test_a_relative_case_root_committed_from_two_directories_would_diverge_but_is_refused_first(tmp_path, monkeypatch):
    """The exact reproduction R3 gave: build a plan whose `case_root` is a
    relative `Path("somecase")` from directory A, then attempt to commit it
    from directory B where a `somecase/` also exists. Without the
    construction-time guard this silently wrote into whichever directory the
    *committing* process happened to be in; with it, the plan cannot be built
    at all."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    (dir_a / "somecase").mkdir(parents=True)
    (dir_b / "somecase").mkdir(parents=True)

    monkeypatch.chdir(dir_a)
    with pytest.raises(ValueError, match="absolute"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("somecase"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_assignment(),), requested_by="test",
        )
    # It was refused before it could be committed from anywhere, so neither
    # candidate directory shows any effect.
    monkeypatch.chdir(dir_b)
    assert list((dir_a / "somecase").iterdir()) == []
    assert list((dir_b / "somecase").iterdir()) == []


# --- 2026-09-23 decision, "a parameter asserts a final state, not only a
# value": `ParameterAssignment` gained `operation` (`set`/`ensure`/`remove`).
# `set` is the default and every assignment built before this field existed
# is implicitly one -- the tests above never pass `operation` at all, and
# still construct, which is itself part of what "the default matches prior
# behaviour" means. These test the new field directly. ---


def test_operation_defaults_to_set():
    assert _assignment().operation == "set"


def test_ensure_behaves_like_set_but_is_a_distinct_operation():
    assignment = _assignment(operation="ensure")
    assert assignment.operation == "ensure"
    assert assignment.value == 0.1


def test_an_unknown_operation_is_refused_by_name():
    with pytest.raises(ValueError, match="banana"):
        _assignment(operation="banana")


def test_remove_forbids_a_value():
    """`remove` asserts the key is absent -- a different claim from "has this
    value", the same reasoning `Precondition` already applies to
    `must_be_absent`/`digest`."""
    with pytest.raises(ValueError, match="value"):
        _assignment(operation="remove", value=0.1)


def test_remove_with_no_value_constructs():
    assignment = _assignment(operation="remove", value=None)
    assert assignment.operation == "remove"
    assert assignment.value is None


def test_set_requires_a_value():
    with pytest.raises(ValueError, match="value"):
        _assignment(operation="set", value=None)


def test_ensure_requires_a_value():
    with pytest.raises(ValueError, match="value"):
        _assignment(operation="ensure", value=None)


def test_remove_still_checks_value_kind_is_known():
    """`remove` skips "does the value fit", since there is no value -- it
    does not skip "is value_kind itself a real kind"."""
    with pytest.raises(ValueError, match="banana"):
        _assignment(operation="remove", value=None, value_kind="banana")


def test_remove_round_trips_through_json():
    assignment = _assignment(operation="remove", value=None)
    payload = assignment.to_json()
    assert payload["operation"] == "remove"
    assert payload["value"] is None
    restored = case_write.ParameterAssignment.from_json(payload)
    assert restored == assignment


def test_a_plan_written_before_operation_existed_reads_back_as_set():
    """`from_json` on a payload with no `operation` key -- what every plan
    written before this field existed looks like -- must read back as `set`,
    not raise and not invent a different default silently."""
    payload = _assignment().to_json()
    del payload["operation"]
    restored = case_write.ParameterAssignment.from_json(payload)
    assert restored.operation == "set"


def test_operation_changes_the_assignment_digest():
    """Two assignments differing only in `operation` must serialize
    differently -- otherwise a plan could not distinguish "set this key" from
    "remove this key" once digested, which is the entire point of adding the
    field (2026-09-23 decision)."""
    set_assignment = _assignment(operation="set")
    ensure_assignment = _assignment(operation="ensure")
    assert (
        case_write.canonical_json(set_assignment.to_json())
        != case_write.canonical_json(ensure_assignment.to_json())
    )


def test_a_clone_and_patch_request_accepts_a_remove_operation():
    """The request-level construction path -- not just the bare dataclass --
    accepts a `remove` assignment. Same slot-uniqueness rule as any other
    assignment: `CaseMutationRequest` does not know or care what operation
    occupies a slot, only that no two assignments claim the same one."""
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case").resolve(),
        adapter_id="org.a", workflow="w", source_artifacts=(),
        parameters=(_assignment(operation="remove", value=None),),
        requested_by="test",
    )
    assert request.parameters[0].operation == "remove"
