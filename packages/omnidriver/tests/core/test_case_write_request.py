"""A mutation request names its mode, its owner, and its sources.

Three creation modes with different prerequisites, deliberately not collapsed:

``clone_and_patch``  an existing case is edited. Source: that case.
``synthesize``       a case is built from a catalog. Needs explicit source
                     artifacts -- a mesh, a template tree -- which a patch does
                     not.
``generated_input``  an operation authors one input file.

The refuted draft had two kinds, ``patch`` and ``synthesize``, and described
them as "the same operation at different arities". They are not: a synthesis
with no source artifact declared is a case built from nothing, and that is how
asset-free synthesis came to look like a supported mode.
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


# --- R2 finding 7: each mode's stated prerequisite is enforced, not merely
# documented. Decided per mode: `generated_input` means exactly one document
# (zero parameters is zero documents, also refused); `clone_and_patch` means
# at least one parameter (a patch that patches nothing is not a creation, it
# is a no-op masquerading as one); `synthesize` already required a non-empty
# source_artifacts, and now every declared artifact must be a real,
# non-whitespace identifier -- an empty string names nothing. ---


def test_a_patch_with_no_parameters_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(), requested_by="test",
        )


def test_generated_input_with_no_parameters_is_refused():
    """Zero parameters is zero documents authored, not one."""
    with pytest.raises(ValueError, match="exactly one"):
        case_write.CaseMutationRequest(
            mode="generated_input", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(), requested_by="test",
        )


def test_generated_input_with_more_than_one_document_is_refused():
    """Documented as "one input file is authored by an operation"; a request
    naming three documents violated that with no check catching it."""
    with pytest.raises(ValueError, match="exactly one"):
        case_write.CaseMutationRequest(
            mode="generated_input", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(
                _assignment(document="constant/a"),
                _assignment(qualified_id="$CARDIAC_CONDUCTIVITY.g", document="constant/b"),
            ),
            requested_by="test",
        )


def test_generated_input_with_exactly_one_document_is_accepted():
    request = case_write.CaseMutationRequest(
        mode="generated_input", case_root=Path("/tmp/case"),
        adapter_id="org.a", workflow="w", source_artifacts=(),
        parameters=(_assignment(),), requested_by="test",
    )
    assert request.mode == "generated_input"


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
