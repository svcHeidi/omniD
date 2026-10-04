"""Commit is core's, and it is recoverable."""
import os
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write

_root_makes_chmod_tests_meaningless = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the write-permission bit this test injects a failure with",
)


def _parameter():
    """The transaction executor itself does not read this parameter; it exists only to satisfy `CaseMutationRequest.__post_init__`."""
    return case_write.ParameterAssignment(
        qualified_id="$TEST.value", owner="org.a", document="constant/a",
        key_path=("value",), value=1.0, value_kind="scalar",
        source="case",
    )


def _plan(case_root: Path, files):
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.a",
        workflow="w", source_artifacts=(), parameters=(_parameter(),),
        requested_by="test",
    )
    return case_write.CaseWritePlan(
        request=request, files=tuple(files),
        semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )


def _rendered(path, content, *, exists_before=False, before_digest=None, mode=None):
    return case_write.RenderedFile(
        path=path, content=content, mode=mode, exists_before=exists_before,
        before_digest=before_digest, renderer_id="org.r", format="f",
    )


def test_a_plan_writes_every_file_and_records_their_digests(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"one\n"),
        _rendered("system/b", b"two\n"),
    ])
    record = case_transaction.commit_case_write(
        plan, driver_context=object(),
    )
    assert (tmp_path / "constant" / "a").read_bytes() == b"one\n"
    assert (tmp_path / "system" / "b").read_bytes() == b"two\n"
    assert record.status == "committed"
    assert {entry["path"] for entry in record.committed} == {"constant/a", "system/b"}


@_root_makes_chmod_tests_meaningless
def test_an_overwritten_file_is_restored_when_a_later_write_fails(tmp_path):
    (tmp_path / "constant").mkdir()
    existing = tmp_path / "constant" / "a"
    existing.write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    plan = _plan(tmp_path, [
        _rendered("constant/a", b"replaced\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(),
            )
        assert existing.read_bytes() == b"original\n"
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


@_root_makes_chmod_tests_meaningless
def test_a_newly_created_file_is_removed_on_rollback(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("constant/new", b"one\n"),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(),
            )
        assert not (tmp_path / "constant" / "new").exists()
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


@_root_makes_chmod_tests_meaningless
def test_a_directory_created_only_for_the_transaction_is_removed_on_rollback(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("brand/new/dir/file", b"one\n"),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(),
            )
        assert not (tmp_path / "brand").exists()
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_file_mode_is_preserved_across_replacement(tmp_path):
    (tmp_path / "constant").mkdir()
    script = tmp_path / "constant" / "Allrun"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o755)
    before = case_write._digest_bytes(b"#!/bin/sh\n")
    plan = _plan(tmp_path, [
        _rendered("constant/Allrun", b"#!/bin/sh\necho hi\n",
                  exists_before=True, before_digest=before, mode=0o755),
    ])
    case_transaction.commit_case_write(plan, driver_context=object())
    assert script.stat().st_mode & 0o777 == 0o755


def test_a_path_escaping_the_case_is_refused_at_commit_too(tmp_path):
    """`RenderedFile` refuses it at construction."""
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "escape").symlink_to(outside / "target")
    plan = _plan(tmp_path, [_rendered("constant/escape", b"x\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="symlink"):
        case_transaction.commit_case_write(plan, driver_context=object())


def test_a_second_attempt_under_a_held_lease_is_refused(tmp_path):
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease

    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with acquire_case_lease(tmp_path):
        with pytest.raises(case_transaction.CaseTransactionError, match="lease"):
            case_transaction.commit_case_write(
                plan, driver_context=object(),
            )


def test_case_lease_held_reuses_the_callers_own_lease(tmp_path):
    """`--apply` calls this from inside `cli.py`'s own already-held case lease (`_dispatch_context`)."""
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease

    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with acquire_case_lease(tmp_path):
        record = case_transaction.commit_case_write(
            plan, driver_context=object(),
            case_lease_held=True,
        )
    assert record.status == "committed"
    assert (tmp_path / "constant" / "a").read_bytes() == b"one\n"
    # The caller's lease is untouched -- released only when the caller's own
    # `with` block exits, not early by this commit.
    assert not case_transaction.pending_transaction(tmp_path)


def test_case_lease_held_refuses_an_unverified_claim(tmp_path):
    """`case_lease_held=True` is checked, not merely trusted: a caller that does not actually hold the lease is refused loudly, not left to proceed with no serialization at all."""
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="case_lease_held"):
        case_transaction.commit_case_write(
            plan, driver_context=object(),
            case_lease_held=True,
        )
    assert not (tmp_path / "constant" / "a").exists()


def test_the_journal_is_removed_after_a_clean_commit(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    case_transaction.commit_case_write(plan, driver_context=object())
    assert not case_transaction.pending_transaction(tmp_path)


# --------------------------------------------------------------------------
# An unwrapped PermissionError must not escape commit_case_write. mode=0o000 is
# a plan-legal RenderedFile.mode, so this is reachable by ordinary use.
# --------------------------------------------------------------------------


@_root_makes_chmod_tests_meaningless
def test_an_unreadable_existing_file_is_wrapped_not_leaked(tmp_path):
    """Commit a `RenderedFile(mode=0o000)`, then a second transaction overwriting that same path."""
    first = _plan(tmp_path, [_rendered("constant/a", b"one\n", mode=0o000)])
    case_transaction.commit_case_write(first, driver_context=object())
    assert (tmp_path / "constant" / "a").stat().st_mode & 0o777 == 0o000

    before = case_write._digest_bytes(b"one\n")
    second = _plan(tmp_path, [
        _rendered("constant/a", b"two\n", exists_before=True, before_digest=before),
    ])
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
            case_transaction.commit_case_write(
                second, driver_context=object(),
            )
    finally:
        (tmp_path / "constant" / "a").chmod(0o644)


# --------------------------------------------------------------------------
# When the case root does not resolve, the refusal must name that real
# cause, not a generic "write lease is already held".
# --------------------------------------------------------------------------


def test_a_missing_case_root_reports_the_real_cause_not_a_held_lease(tmp_path):
    missing = tmp_path / "does-not-exist-yet"
    plan = _plan(missing, [_rendered("constant/a", b"one\n")])
    with pytest.raises(case_transaction.CaseTransactionError) as excinfo:
        case_transaction.commit_case_write(plan, driver_context=object())
    message = str(excinfo.value)
    assert "does not exist" in message
    assert "already held" not in message


# ---------------------------------------------------------------------------
# A renderer's ``exists_before`` claim is rechecked against the real filesystem
# before any write: committing a wrong "this file is new" would replace the
# whole file with only the just-rendered keys.
# ---------------------------------------------------------------------------


def test_commit_refuses_a_render_claiming_new_when_the_target_already_exists_on_disk(tmp_path):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_text("already here\n")
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"replaced\n", exists_before=False),
    ])
    with pytest.raises(case_transaction.CaseTransactionError, match="exists_before"):
        case_transaction.commit_case_write(plan, driver_context=object())
    # Refused BEFORE any write: the real file is untouched.
    assert (tmp_path / "constant" / "a").read_text() == "already here\n"


def test_commit_refuses_a_render_claiming_existing_when_the_target_is_missing(tmp_path):
    plan = _plan(tmp_path, [
        _rendered(
            "constant/a", b"replaced\n", exists_before=True,
            before_digest=case_write._digest_bytes(b"whatever was assumed\n"),
        ),
    ])
    with pytest.raises(case_transaction.CaseTransactionError, match="exists_before"):
        case_transaction.commit_case_write(plan, driver_context=object())
    assert not (tmp_path / "constant" / "a").exists()


def test_a_verify_that_refuses_rolls_the_commit_back_and_raises_as_it_is(tmp_path):
    (tmp_path / "constant").mkdir()
    existing = tmp_path / "constant" / "a"
    existing.write_bytes(b"original\n")
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"replaced\n", exists_before=True,
                  before_digest=case_write._digest_bytes(b"original\n")),
        _rendered("constant/new", b"one\n"),
    ])

    def refuse():
        assert existing.read_bytes() == b"replaced\n"
        raise ValueError("the case breaks a rule")

    with pytest.raises(ValueError, match="breaks a rule"):
        case_transaction.commit_case_write(plan, driver_context=object(), verify=refuse)

    assert existing.read_bytes() == b"original\n"
    assert not (tmp_path / "constant" / "new").exists()
    assert case_transaction.pending_transaction(tmp_path) is None
    assert not (tmp_path / ".omnidriver" / "case-transactions").exists()
