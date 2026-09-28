"""An interrupted or retried transaction has one correct outcome."""
import json
import os
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write


def _parameter():
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


def _rendered(path, content, **kwargs):
    return case_write.RenderedFile(
        path=path, content=content, mode=kwargs.get("mode"),
        exists_before=kwargs.get("exists_before", False),
        before_digest=kwargs.get("before_digest"),
        renderer_id="org.r", format="f",
    )


def test_an_interrupted_transaction_is_recoverable(tmp_path, monkeypatch):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    calls = {"n": 0}
    real = case_transaction._write_one

    def _die_after_first(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("simulated interruption")
        return real(*args, **kwargs)

    monkeypatch.setattr(case_transaction, "_write_one", _die_after_first)
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/b", b"two\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)

    # The journal survived; the case has not been restored yet.
    assert case_transaction.pending_transaction(tmp_path)

    record = case_transaction.recover_case_transaction(tmp_path)
    assert record.status == "rolled_back"
    assert (tmp_path / "constant" / "a").read_bytes() == b"original\n"
    assert not (tmp_path / "constant" / "b").exists()
    assert not case_transaction.pending_transaction(tmp_path)


def test_a_journal_with_an_unrecognised_state_is_refused(tmp_path):
    """`_read_journal` must validate `state` against `TRANSACTION_STATES`, not accept any value."""
    (tmp_path / ".omnidriver").mkdir(parents=True, exist_ok=True)
    case_transaction._write_journal(tmp_path, {
        "transaction_id": "t-bogus", "state": "definitely_not_a_real_state",
        "plan_digest": "0" * 64, "before_images": [],
    })
    with pytest.raises(case_transaction.CaseTransactionError, match="definitely_not_a_real_state"):
        case_transaction.pending_transaction(tmp_path)


def test_an_unrecovered_journal_blocks_a_new_commit(tmp_path):
    (tmp_path / ".omnidriver").mkdir(parents=True, exist_ok=True)
    case_transaction._write_journal(tmp_path, {
        "transaction_id": "t-stuck", "state": "applying",
        "plan_digest": "0" * 64, "before_images": [],
    })
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="t-stuck"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_replaying_a_completed_transaction_returns_its_record(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    first = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    (tmp_path / "constant" / "a").write_bytes(b"someone else edited this\n")
    second = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    assert second.transaction_id == first.transaction_id
    assert second.status == "committed"
    # Not reapplied: a retry after an uncertain response must not overwrite a
    # case that moved on.
    assert (tmp_path / "constant" / "a").read_bytes() == b"someone else edited this\n"


def test_a_replay_with_a_different_plan_under_one_id_is_refused(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-2",
    )
    other = _plan(tmp_path, [_rendered("constant/a", b"different\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="t-2"):
        case_transaction.commit_case_write(
            other, driver_context=object(), execution_env=None, transaction_id="t-2",
        )


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the write-permission bit this test injects a failure with",
)
def test_a_rollback_that_itself_fails_leaves_the_journal_and_says_so(tmp_path, monkeypatch):
    """The worst case must be loud."""
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    monkeypatch.setattr(
        case_transaction, "_restore_one",
        lambda *a, **k: (_ for _ in ()).throw(OSError("restore failed")),
    )
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="rollback"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert case_transaction.pending_transaction(tmp_path)
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_persisted_plan_round_trips(tmp_path):
    """`CaseWritePlan.from_json` was already implemented before this task, not left as a `NotImplementedError` the way the plan's own snippet describes (a stale plan claim, reported rather than followed): `RenderedFile` embeds its content as base64 directly, so `to_json()`/`from_json()` round-trip with no separate ``contents`` side-channel needed."""
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    payload = json.loads(case_write.canonical_json(plan.to_json()))
    restored = case_write.CaseWritePlan.from_json(payload)
    assert restored.plan_digest == plan.plan_digest
