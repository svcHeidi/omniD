"""A reviewed plan contains everything that will happen, and nothing that has.

Closes proposal defect W1. The previous draft's plan omitted values from its
JSON, held mutable payloads inside frozen records, and carried execution-time
before-images as plan fields.

A plan is reviewable only if what an agent reads is what will be written, and
stable only if the bytes it hashes cannot change afterwards.
"""

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
                binding={}, value="TT06", value_kind="word", source="case",
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
        preconditions=(
            case_write.Precondition(
                kind="file", target="constant/electroProperties",
                digest="a" * 64, must_be_absent=False,
            ),
        ),
        semantic_owner_id="org.cardiacfoam",
        stack_identity="deadbeef" * 8,
        created_at="2026-09-22T00:00:00Z",
    )
    fields.update(overrides)
    return case_write.CaseWritePlan(**fields)


def test_the_serialized_plan_contains_every_value_that_will_be_written():
    payload = _plan().to_json()
    parameter = payload["request"]["parameters"][0]
    assert parameter["value"] == "TT06"
    assert parameter["expanded_key_path"] == ["ionicModel"]
    rendered = payload["files"][0]
    assert rendered["content_digest"]
    assert rendered["path"] == "constant/electroProperties"
    assert rendered["format"] == "openfoam_dictionary"


def test_a_plan_round_trips_through_json_unchanged():
    plan = _plan()
    assert case_write.CaseWritePlan.from_json(plan.to_json()).plan_digest == plan.plan_digest


def test_a_frozen_plan_has_no_mutable_interior():
    """W1: `frozen=True` stops rebinding a field, not mutating what it points
    at. A reviewed plan whose reviewed contents can change is not reviewed."""
    plan = _plan()
    with pytest.raises(Exception):
        plan.files = ()
    parameter = plan.request.parameters[0]
    with pytest.raises(TypeError):
        parameter.binding["injected"] = "value"


def test_a_dict_valued_parameter_is_frozen_too():
    assignment = case_write.ParameterAssignment(
        qualified_id="$ELECTRO.coeffs", owner="org.a",
        document="constant/electroProperties", key_path=("coeffs",),
        binding={}, value={"gNa": 1.0}, value_kind="dictionary", source="template",
    )
    with pytest.raises(TypeError):
        assignment.value["gNa"] = 2.0


def test_a_plan_carries_no_before_image():
    """W1: a before-image is execution state. The journal owns it; a plan that
    gains one during execution is not the plan that was reviewed."""
    fields = {field.name for field in case_write.CaseWritePlan.__dataclass_fields__.values()}
    assert "before" not in fields
    rendered_fields = {
        field.name for field in case_write.RenderedFile.__dataclass_fields__.values()
    }
    assert "before" not in rendered_fields
    # A digest of the prior content is evidence and belongs here; the bytes
    # themselves are recovery state and do not.
    assert "before_digest" in rendered_fields


def test_the_digest_is_stable_across_processes():
    """The digest is what a stale-plan check compares. Dict iteration order,
    float repr and key order must not enter it."""
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent(
        """
        from pathlib import Path
        from omnidriver.core import case_write
        request = case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(
                case_write.ParameterAssignment(
                    qualified_id="$E.coeffs", owner="org.a",
                    document="constant/electroProperties", key_path=("coeffs",),
                    binding={}, value={"z": 1.0, "a": 2.0, "m": 3.0},
                    value_kind="dictionary", source="template",
                ),
            ),
            requested_by="probe",
        )
        plan = case_write.CaseWritePlan(
            request=request,
            files=(case_write.RenderedFile(
                path="constant/electroProperties", content=b"x",
                mode=None, exists_before=False, before_digest=None,
                renderer_id="org.openfoam", format="openfoam_dictionary",
            ),),
            preconditions=(),
            semantic_owner_id="org.a",
            stack_identity="0" * 64,
            created_at="2026-09-22T00:00:00Z",
        )
        print(plan.plan_digest)
        """
    )
    digests = set()
    for seed in ("0", "1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        digests.add(result.stdout.strip())
    assert len(digests) == 1, digests


def test_a_rendered_file_outside_the_case_is_refused():
    with pytest.raises(ValueError, match="case-relative"):
        _file(path="/etc/passwd")
    with pytest.raises(ValueError, match="escape"):
        _file(path="../outside")


def test_two_rendered_files_at_one_path_are_refused():
    with pytest.raises(ValueError, match="written twice"):
        _plan(files=(_file(), _file(content=b"other\n")))


def test_a_schema_version_mismatch_is_refused_with_the_versions_named():
    payload = _plan().to_json()
    payload["schema_version"] = 999
    with pytest.raises(ValueError, match="999"):
        case_write.CaseWritePlan.from_json(payload)


def test_an_unknown_precondition_kind_is_refused():
    with pytest.raises(ValueError, match="guess"):
        case_write.Precondition(
            kind="guess", target="x", digest=None, must_be_absent=False,
        )


def test_an_absence_precondition_carries_no_digest():
    """"This file must not exist" and "this file must have digest X" are
    different claims. A precondition asserting both is incoherent."""
    with pytest.raises(ValueError, match="absent"):
        case_write.Precondition(
            kind="absence", target="constant/x", digest="a" * 64, must_be_absent=True,
        )


def test_a_record_is_separate_from_its_plan():
    """The committed result is not a field of the plan. Recording it there is
    how a reviewed artifact comes to differ from what was reviewed."""
    plan = _plan()
    record = case_write.CaseWriteRecord(
        transaction_id="t1", plan_id=plan.plan_id, plan_digest=plan.plan_digest,
        committed=({"path": "constant/electroProperties", "digest": "b" * 64},),
        evidence=(), status="committed",
    )
    assert record.plan_digest == plan.plan_digest
    assert "committed" not in {
        field.name for field in case_write.CaseWritePlan.__dataclass_fields__.values()
    }


# --- R2 finding 3: declared-tuple fields accepted a list, and appending to it
# after construction bypassed the checks that had already run and mutated
# "frozen" state -- W1 verbatim, fixed for exactly one field before this. ---


def test_a_list_passed_as_files_cannot_be_mutated_after_construction():
    """Passing a list where the field is declared `tuple[...]` used to be
    accepted, and the SAME list object was stored -- so appending a
    colliding path after construction bypassed the duplicate-path check that
    had already run and silently changed `plan_digest`. `files` must be a
    real tuple, which has no `.append`."""
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
        binding={}, value="TT06", value_kind="word", source="case",
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
    """`slot()` reads `key_path`. A list `key_path` let a caller append to it
    after `CaseMutationRequest`'s duplicate-slot check already ran against the
    pre-append value, so the check passed against one slot while the
    assignment silently occupied another."""
    key_path = ["ionicModel"]
    assignment = case_write.ParameterAssignment(
        qualified_id="$E.ionicModel", owner="org.a",
        document="constant/electroProperties", key_path=key_path,
        binding={}, value="TT06", value_kind="word", source="case",
    )
    assert isinstance(assignment.key_path, tuple)
    key_path.append("extra")
    assert assignment.slot() == "constant/electroProperties::ionicModel"


def test_a_committed_entry_is_frozen_not_a_live_dict():
    plan = _plan()
    record = case_write.CaseWriteRecord(
        transaction_id="t1", plan_id=plan.plan_id, plan_digest=plan.plan_digest,
        committed=({"path": "constant/electroProperties", "digest": "b" * 64},),
        evidence=({"source": "runtime"},), status="committed",
    )
    with pytest.raises(TypeError):
        record.committed[0]["digest"] = "9" * 64
    with pytest.raises(TypeError):
        record.evidence[0]["source"] = "tampered"


def test_a_resolved_mutation_target_is_frozen_not_a_live_dict():
    resolved = case_write.ResolvedMutation(
        request=_request(), targets=({"format": "openfoam_dictionary", "path": "x"},),
        preconditions=(), expected_effects=(), semantic_owner_id="org.a",
    )
    with pytest.raises(TypeError):
        resolved.targets[0]["path"] = "y"


def test_a_mapping_payload_must_use_string_keys():
    """JSON has no other key type. An int key silently becomes a string on a
    real JSON round trip without changing the digest, which is how a
    reviewed plan could drift after review unnoticed."""
    with pytest.raises(TypeError, match="string"):
        case_write.CaseWriteRecord(
            transaction_id="t1", plan_id="p", plan_digest="d" * 16,
            committed=({1: "a"},), evidence=(), status="committed",
        )


def test_a_mapping_payload_rejects_a_non_finite_float():
    with pytest.raises(ValueError, match="non-finite"):
        case_write.CaseWriteRecord(
            transaction_id="t1", plan_id="p", plan_digest="d" * 16,
            committed=({"magnitude": float("nan")},), evidence=(), status="committed",
        )


def test_a_mapping_payload_rejects_an_arbitrary_object():
    """`_freeze` used to return an unrecognised type unchanged, while
    promising "a plan payload must be JSON-shaped and immutable"."""

    class _Opaque:
        pass

    with pytest.raises(TypeError, match="JSON-shaped"):
        case_write.CaseWriteRecord(
            transaction_id="t1", plan_id="p", plan_digest="d" * 16,
            committed=({"thing": _Opaque()},), evidence=(), status="committed",
        )
