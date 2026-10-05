"""A reviewed plan contains everything that will happen, and nothing that has."""

from pathlib import Path

import pytest

from omnidriver.core import case_write


def _request():
    return case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.cardiacfoam", workflow="entry",
        source_artifacts=(),
        parameters=(
            case_write.ParameterAssignment(
                qualified_id="$ELECTRO.ionicModel", owner="org.cardiacfoam",
                document="constant/electroProperties", key_path=("ionicModel",),
                value="TT06", value_kind="word", source="case",
            ),
        ),
        requested_by="test",
    )


def _file(**overrides):
    fields = dict(
        path="constant/electroProperties",
        content=b"ionicModel TT06;\n",
        mode=None,
        exists_before=True,
        before_digest="a" * 64,
        renderer_id="org.openfoam",
        format="openfoam_dictionary",
    )
    fields.update(overrides)
    return case_write.RenderedFile(**fields)


def _plan(**overrides):
    fields = dict(
        request=_request(),
        files=(_file(),),
        semantic_owner_id="org.cardiacfoam",
        stack_identity="deadbeef" * 8,
    )
    fields.update(overrides)
    return case_write.CaseWritePlan(**fields)


def test_a_frozen_plan_has_no_mutable_interior():
    """`frozen=True` stops rebinding a field, not mutating what it points at."""
    plan = _plan()
    with pytest.raises(Exception):
        plan.files = ()
    with pytest.raises(AttributeError):
        plan.request.parameters[0].qualified_id = "tampered"


def test_a_dict_valued_parameter_is_frozen_too():
    """The closed value_kind vocabulary has no untyped "dictionary" escape; no current DictEntry declaration has that shape."""
    assignment = case_write.ParameterAssignment(
        qualified_id="$ELECTRO.coeffs", owner="org.a",
        document="constant/electroProperties", key_path=("coeffs",),
        value={"value": 1.0, "dimensions": (0, -3, 0, 0, 0, 1, 0)},
        value_kind="dimensioned_scalar", source="template",
    )
    with pytest.raises(TypeError):
        assignment.value["value"] = 2.0


def test_a_plan_carries_no_before_image():
    """A before-image is execution state."""
    fields = {field.name for field in case_write.CaseWritePlan.__dataclass_fields__.values()}
    assert "before" not in fields
    rendered_fields = {
        field.name for field in case_write.RenderedFile.__dataclass_fields__.values()
    }
    assert "before" not in rendered_fields
    # A digest of the prior content is evidence and belongs here; the bytes
    # themselves are rollback state and do not.
    assert "before_digest" in rendered_fields


def test_a_rendered_file_outside_the_case_is_refused():
    with pytest.raises(ValueError, match="case-relative"):
        _file(path="/etc/passwd")
    with pytest.raises(ValueError, match="escape"):
        _file(path="../outside")


def test_two_rendered_files_at_one_path_are_refused():
    with pytest.raises(ValueError, match="written twice"):
        _plan(files=(_file(), _file(content=b"other\n")))


# A list passed for a declared `tuple[...]` field must be coerced, not stored
# by reference -- otherwise appending to the caller's list after construction
# would bypass the duplicate-path check and mutate "frozen" state.


def test_a_list_passed_as_files_cannot_be_mutated_after_construction():
    original = [_file()]
    plan = _plan(files=original)
    assert isinstance(plan.files, tuple)
    original.append(_file(path="system/evil", content=b"rm -rf /"))
    assert len(plan.files) == 1, "mutating the caller's list must not reach the plan"
    with pytest.raises(AttributeError):
        plan.files.append(_file(path="system/evil", content=b"rm -rf /"))


def test_a_list_passed_as_parameters_is_coerced_and_the_duplicate_check_survives_mutation():
    conductivity_dup = case_write.ParameterAssignment(
        qualified_id="$E.ionicModel", owner="org.a",
        document="constant/electroProperties", key_path=("ionicModel",),
        value="TT06", value_kind="word", source="case",
    )
    original = [conductivity_dup]
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.a", workflow="w", source_artifacts=(),
        parameters=original, requested_by="test",
    )
    assert isinstance(request.parameters, tuple)
    original.append(conductivity_dup)
    assert len(request.parameters) == 1, "mutating the caller's list must not reach the request"


def test_a_list_passed_as_key_path_cannot_retroactively_change_the_slot():
    """`slot()` reads `key_path`."""
    key_path = ["ionicModel"]
    assignment = case_write.ParameterAssignment(
        qualified_id="$E.ionicModel", owner="org.a",
        document="constant/electroProperties", key_path=key_path,
        value="TT06", value_kind="word", source="case",
    )
    assert isinstance(assignment.key_path, tuple)
    key_path.append("extra")
    assert assignment.slot() == "constant/electroProperties::ionicModel"


def test_a_resolved_mutation_target_is_frozen_not_a_live_dict():
    resolved = case_write.ResolvedMutation(
        request=_request(), targets=({"format": "openfoam_dictionary", "path": "x"},),
        expected_effects=(), semantic_owner_id="org.a",
    )
    with pytest.raises(TypeError):
        resolved.targets[0]["path"] = "y"


# --- Cheap correctness items. ---


def test_a_plan_with_zero_files_is_refused():
    with pytest.raises(ValueError, match="at least one file"):
        _plan(files=())


def _opaque_target(value):
    return case_write.ResolvedMutation(
        request=_request(), targets=({"thing": value},), expected_effects=(), semantic_owner_id="org.a",
    )


def test_a_target_must_use_string_keys():
    """JSON has no other key type."""
    with pytest.raises(TypeError, match="string"):
        case_write.ResolvedMutation(
            request=_request(), targets=({1: "a"},), expected_effects=(), semantic_owner_id="org.a",
        )


def test_a_target_rejects_a_non_finite_float():
    with pytest.raises(ValueError, match="non-finite"):
        _opaque_target(float("nan"))


def test_a_target_rejects_an_arbitrary_object():
    """`_freeze` must refuse an unrecognised type, not return it unchanged and silently break the "JSON-shaped and immutable" promise."""

    class _Opaque:
        pass

    with pytest.raises(TypeError, match="JSON-shaped"):
        _opaque_target(_Opaque())
