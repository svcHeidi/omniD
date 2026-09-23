"""An interrupted or retried transaction has one correct outcome.

Three situations, three answers:

* Interrupted mid-apply -> recovery restores the before-images and the case
  is back where it started. Until recovery runs, dispatch is blocked: a case
  whose inputs are half-written is not a case whose inputs are known.
* Retried after an uncertain response, same transaction id -> the existing
  record is returned. Reapplying would write over a case that may have moved
  on.
* Retried with a plan whose preconditions no longer hold -> refused as stale,
  naming what changed (covered by test_case_transaction.py's precondition
  tests; this file covers the transaction-id replay path instead).
"""
import json
import os
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write
from omnidriver.core.planning_types import SimulationAuditItem
from omnidriver.core.runtime.launch_readiness import is_launchable


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
    """R3 finding 5 (2026-09-23): `TRANSACTION_STATES` was declared but never
    validated by `_read_journal` -- any `state` value was accepted.
    Behaviour was safe today (rollback is unconditional on this field), but
    the invariant was dead. Matches
    `remediation_transaction.read_remediation_transaction`'s own
    status-validation pattern."""
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
    """The worst case must be loud. A failed rollback leaves a case in an
    unknown state, and the journal is the only record of what it was."""
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
    """`CaseWritePlan.from_json` was already implemented before this task, not
    left as a `NotImplementedError` the way the plan's own snippet describes
    (a stale plan claim, reported rather than followed): `RenderedFile`
    embeds its content as base64 directly, so `to_json()`/`from_json()`
    round-trip with no separate ``contents`` side-channel needed."""
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    payload = json.loads(case_write.canonical_json(plan.to_json()))
    restored = case_write.CaseWritePlan.from_json(payload)
    assert restored.plan_digest == plan.plan_digest


def test_an_unrecovered_transaction_is_reported_as_unavailable_coverage(tmp_path):
    """Task 6's dispatch-facing seam: an unrecovered journal reuses G0 Task
    8's existing coverage gate (`SimulationAuditItem`/`is_launchable`)
    rather than a second bespoke check. Not wired to any dispatch call site
    by this batch -- see `unrecovered_transaction_audit`'s own docstring."""
    (tmp_path / ".omnidriver").mkdir(parents=True, exist_ok=True)
    case_transaction._write_journal(tmp_path, {
        "transaction_id": "t-stuck", "state": "applying",
        "plan_digest": "0" * 64, "before_images": [],
    })
    item = case_transaction.unrecovered_transaction_audit(tmp_path)
    assert isinstance(item, SimulationAuditItem)
    assert item.stage == "case_inputs"
    assert item.status == "unavailable"

    readiness = is_launchable(plan_status="ok", simulation_audit=(item,))
    assert not readiness.launchable
    assert not readiness.coverage_ok


def test_no_unrecovered_transaction_is_no_coverage_gap(tmp_path):
    assert case_transaction.unrecovered_transaction_audit(tmp_path) is None
