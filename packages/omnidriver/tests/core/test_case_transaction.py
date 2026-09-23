"""Commit is core's, and it is recoverable.

Per-file atomic replacement plus a journal. That gives: recovery from an
interruption, rollback of a partially applied plan, and a framework reader
never seeing a half-written file. It does NOT give simultaneous atomic
visibility of several files to an arbitrary outside process -- proposal defect
W2 described it as an atomic case write, and it is not one. The tests below
assert what is true.

The chmod-based failure-injection tests do not behave as written when run as
root (root ignores a directory's write permission bit), so they are guarded
with ``skipif(os.geteuid() == 0, ...)``: a test that silently passes because
it could not fail is worse than a skip that says why.
"""
import os
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write

_root_makes_chmod_tests_meaningless = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the write-permission bit this test injects a failure with",
)


def _parameter():
    """A request needs at least one parameter for `clone_and_patch` (R2 finding
    7, added after this plan's Task 5 snippet was written) -- the transaction
    executor itself does not read this; it exists only to satisfy
    `CaseMutationRequest.__post_init__`."""
    return case_write.ParameterAssignment(
        qualified_id="$TEST.value", owner="org.a", document="constant/a",
        key_path=("value",), binding={}, value=1.0, value_kind="scalar",
        source="case",
    )


def _plan(case_root: Path, files, preconditions=()):
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.a",
        workflow="w", source_artifacts=(), parameters=(_parameter(),),
        requested_by="test",
    )
    return case_write.CaseWritePlan(
        request=request, files=tuple(files), preconditions=tuple(preconditions),
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
        plan, driver_context=object(), execution_env=None,
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
                plan, driver_context=object(), execution_env=None,
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
                plan, driver_context=object(), execution_env=None,
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
                plan, driver_context=object(), execution_env=None,
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
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert script.stat().st_mode & 0o777 == 0o755


def test_a_failed_precondition_refuses_before_any_write(tmp_path):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"changed since planning\n")
    plan = _plan(
        tmp_path,
        [_rendered("constant/a", b"new\n", exists_before=True, before_digest="a" * 64)],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/a", digest="a" * 64, must_be_absent=False,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert (tmp_path / "constant" / "a").read_bytes() == b"changed since planning\n"


def test_an_absence_precondition_that_no_longer_holds_refuses(tmp_path):
    """A file appearing at a higher-priority include location changes which
    file the run reads (audit finding F2). Its absence was a precondition."""
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "shadow").write_bytes(b"appeared\n")
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="absence", target="site/shadow", digest=None, must_be_absent=True,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="site/shadow"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_a_path_escaping_the_case_is_refused_at_commit_too(tmp_path):
    """`RenderedFile` refuses it at construction. Commit checks again against
    the resolved real path, because a symlink can move a legal path outside."""
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "escape").symlink_to(outside / "target")
    plan = _plan(tmp_path, [_rendered("constant/escape", b"x\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="symlink"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_a_second_attempt_under_a_held_lease_is_refused(tmp_path):
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease

    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with acquire_case_lease(tmp_path):
        with pytest.raises(case_transaction.CaseTransactionError, match="lease"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )


def test_the_journal_is_removed_after_a_clean_commit(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert not case_transaction.pending_transaction(tmp_path)


# --------------------------------------------------------------------------
# R3 blocker 1 (2026-09-23): an unwrapped PermissionError escaped
# commit_case_write. mode=0o000 is a plan-legal RenderedFile.mode, so this is
# reachable by ordinary use -- not a monkeypatch, the real public path.
# --------------------------------------------------------------------------


@_root_makes_chmod_tests_meaningless
def test_an_unreadable_existing_file_is_wrapped_not_leaked(tmp_path):
    """Commit a `RenderedFile(mode=0o000)`, then a second transaction
    overwriting that same path. `_before_image`'s `target.read_bytes()` needs
    read access to snapshot the before-image; it used to raise a bare
    `PermissionError` that escaped past the lease's release and every
    caller's assumption that a commit failure surfaces as
    `CaseTransactionError`."""
    first = _plan(tmp_path, [_rendered("constant/a", b"one\n", mode=0o000)])
    case_transaction.commit_case_write(first, driver_context=object(), execution_env=None)
    assert (tmp_path / "constant" / "a").stat().st_mode & 0o777 == 0o000

    before = case_write._digest_bytes(b"one\n")
    second = _plan(tmp_path, [
        _rendered("constant/a", b"two\n", exists_before=True, before_digest=before),
    ])
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
            case_transaction.commit_case_write(
                second, driver_context=object(), execution_env=None,
            )
    finally:
        (tmp_path / "constant" / "a").chmod(0o644)


@_root_makes_chmod_tests_meaningless
def test_an_unreadable_precondition_target_is_wrapped_not_leaked(tmp_path):
    """The same unguarded read existed in `_check_preconditions`."""
    (tmp_path / "constant").mkdir()
    target = tmp_path / "constant" / "locked"
    target.write_bytes(b"secret\n")
    target.chmod(0o000)
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/locked", digest="0" * 64, must_be_absent=False,
        )],
    )
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="constant/locked"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
    finally:
        target.chmod(0o644)
