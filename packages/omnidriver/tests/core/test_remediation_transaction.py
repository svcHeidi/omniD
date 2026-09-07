"""Crash/rejection semantics for case-local remediation journals."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from omnidriver import cli
from omnidriver.core.runtime.attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
)
from omnidriver.core.runtime.remediation_transaction import (
    MARKER_NAME,
    RemediationTransactionError,
    accepted_external_dependencies,
    begin_remediation_transaction,
    finish_remediation_transaction,
    mark_remediation_dispatching,
    read_remediation_transaction,
    record_remediation_outcome,
    require_reusable_case,
    restore_remediation_transaction,
)


@contextmanager
def _owned(case_root: Path, output_dir: Path):
    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            yield


def _begin(case_root: Path, output_dir: Path, *, value: str = "2") -> dict:
    target = case_root / "system" / "controlDict"
    with _owned(case_root, output_dir):
        return begin_remediation_transaction(
            case_root, output_dir=output_dir, step_id="solve",
            overrides=[{"driver_path": "value", "value": value}],
            hypothesis="smaller step improves stability", target_paths=(target,),
        )


def _finish(case_root: Path, transaction: dict, **kwargs) -> dict:
    with _owned(case_root, Path(transaction["output_dir"])):
        return finish_remediation_transaction(case_root, transaction, **kwargs)


def _accepted(case_root: Path, transaction: dict, **kwargs) -> dict:
    with _owned(case_root, Path(transaction["output_dir"])):
        validated = finish_remediation_transaction(
            case_root, transaction, status="validated", **kwargs,
        )
        dispatching = mark_remediation_dispatching(case_root, validated)
        return record_remediation_outcome(
            case_root, dispatching, execution_status="ok", attempt=1,
        )


def _begin_targets(case_root: Path, output_dir: Path, **kwargs) -> dict:
    with _owned(case_root, output_dir):
        return begin_remediation_transaction(case_root, output_dir=output_dir, **kwargs)


def test_interrupted_transaction_blocks_reuse_and_further_mutation(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    transaction = _begin(case_root, tmp_path / "output")

    persisted = json.loads((case_root / MARKER_NAME).read_text())
    assert persisted["transaction_id"] == transaction["transaction_id"]
    assert persisted["status"] == "applying"
    durable = (
        tmp_path / "output" / "remediation_transactions"
        / f"{transaction['transaction_id']}.json"
    )
    assert json.loads(durable.read_text())["hypothesis"] == transaction["hypothesis"]
    with pytest.raises(RemediationTransactionError, match="interrupted"):
        require_reusable_case(case_root, explicit_repair=False)
    with pytest.raises(RemediationTransactionError, match="interrupted"):
        require_reusable_case(case_root, explicit_repair=True)


def test_rejected_candidate_is_retained_and_requires_explicit_repair(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    candidate = case_root / "system" / "controlDict"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("value 2;\n")
    output_dir = tmp_path / "output"
    transaction = _begin(case_root, output_dir)
    rejected = _finish(
        case_root,
        transaction,
        status="rejected",
        effective_resolution=({"inspected_files": [str(candidate)]},),
        error="validation refused the candidate",
    )

    with pytest.raises(RemediationTransactionError, match="rejected"):
        require_reusable_case(case_root, explicit_repair=False)
    require_reusable_case(case_root, explicit_repair=True)
    archive = Path(rejected["candidate_archive"])
    assert (archive / "system" / "controlDict").read_text() == "value 2;\n"
    assert json.loads((archive / "transaction.json").read_text())["status"] == "rejected"


def test_repeated_failed_proposal_is_detected_without_imposing_a_limit(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    first = _begin(case_root, output_dir)
    with _owned(case_root, output_dir):
        validated = finish_remediation_transaction(case_root, first, status="validated")
        dispatching = mark_remediation_dispatching(case_root, validated)
        record_remediation_outcome(
            case_root, dispatching, execution_status="failed", attempt=3,
        )

    repeated = _begin(case_root, output_dir)

    assert repeated["repeats_failed_proposal"] is True
    assert repeated["parent_transaction_id"] == first["transaction_id"]
    assert read_remediation_transaction(case_root)["status"] == "applying"


def test_rollback_preserves_rejected_baseline_refusal(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    first = _begin(case_root, output_dir)
    _finish(
        case_root, first, status="rejected", error="invalid plan",
    )
    second = _begin(case_root, output_dir, value="3")
    _finish(
        case_root, second, status="rolled_back", error="mutation rolled back",
    )

    with pytest.raises(RemediationTransactionError, match="rejected"):
        require_reusable_case(case_root, explicit_repair=False)


def test_rollback_preserves_accepted_baseline_dependencies(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    external = tmp_path / "runtime.cfg"
    external.write_text("value 1;\n")
    first = _begin(case_root, output_dir)
    _accepted(
        case_root, first,
        effective_resolution=({"inspected_files": [str(external)]},),
    )
    second = _begin(case_root, output_dir, value="3")
    _finish(
        case_root, second, status="rolled_back", error="mutation rolled back",
    )

    require_reusable_case(case_root, explicit_repair=False)
    assert accepted_external_dependencies(case_root) == (external.resolve(),)


def test_restore_recovers_exact_multi_file_before_images_and_absence(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    system = case_root / "system"
    system.mkdir(parents=True)
    schemes = system / "fvSchemes"
    solution = system / "fvSolution"
    generated = system / "generatedDict"
    schemes.write_text("scheme baseline;\n")
    solution.write_text("solution baseline;\n")
    schemes.chmod(0o640)
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "scheme", "value": "candidate"}],
        hypothesis="change two coupled numerical dictionaries",
        target_paths=(schemes, solution, generated),
    )
    schemes.write_text("scheme candidate;\n")
    schemes.chmod(0o600)
    solution.write_text("solution candidate;\n")
    generated.write_text("partial new file;\n")

    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            restored = restore_remediation_transaction(
                case_root,
                output_dir=output_dir,
                transaction_id=transaction["transaction_id"],
                expected_revision=transaction["revision"],
                expected_status=transaction["status"],
            )

    assert schemes.read_text() == "scheme baseline;\n"
    assert schemes.stat().st_mode & 0o777 == 0o640
    assert solution.read_text() == "solution baseline;\n"
    assert not generated.exists()
    assert restored["status"] == "rolled_back"
    archive = Path(restored["candidate_archive"])
    assert (archive / "system" / "fvSchemes").read_text() == "scheme candidate;\n"
    assert (archive / "system" / "generatedDict").read_text() == "partial new file;\n"


def test_restore_fails_closed_on_corrupt_backup_without_touching_candidate(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "value", "value": "candidate"}],
        hypothesis="candidate",
        target_paths=(target,),
    )
    target.write_text("candidate")
    backup = output_dir / transaction["target_manifest"][0]["backup_relpath"]
    backup.write_text("corrupt")

    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            with pytest.raises(RemediationTransactionError, match="hash mismatch"):
                restore_remediation_transaction(
                    case_root, output_dir=output_dir,
                    transaction_id=transaction["transaction_id"],
                    expected_revision=transaction["revision"],
                    expected_status=transaction["status"],
                )

    assert target.read_text() == "candidate"
    assert read_remediation_transaction(case_root)["status"] == "applying"


def test_restore_rejects_redirected_backup_manifest(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "value", "value": "candidate"}],
        hypothesis="candidate",
        target_paths=(target,),
    )
    target.write_text("candidate")
    redirected = output_dir / "unrelated"
    redirected.write_text("baseline")
    marker = json.loads((case_root / MARKER_NAME).read_text())
    marker["target_manifest"][0]["backup_relpath"] = "unrelated"
    (case_root / MARKER_NAME).write_text(json.dumps(marker))

    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            with pytest.raises(
                RemediationTransactionError, match="does not match its target",
            ):
                restore_remediation_transaction(
                    case_root, output_dir=output_dir,
                    transaction_id=transaction["transaction_id"],
                    expected_revision=transaction["revision"],
                    expected_status=transaction["status"],
                )

    assert target.read_text() == "candidate"


def test_restore_requires_exact_expected_revision_and_status(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir, step_id="solve", overrides=[], hypothesis="candidate",
        target_paths=(target,),
    )
    target.write_text("candidate")

    with _owned(case_root, output_dir):
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            restore_remediation_transaction(
                case_root, output_dir=output_dir,
                transaction_id=transaction["transaction_id"],
                expected_revision=transaction["revision"] + 1,
                expected_status="validated",
            )

    assert target.read_text() == "candidate"
    assert read_remediation_transaction(case_root)["status"] == "applying"


def test_recover_cli_restores_without_loading_a_plugin_or_dispatching(
    capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir,
        step_id="solve",
        overrides=[{"driver_path": "value", "value": "candidate"}],
        hypothesis="candidate",
        target_paths=(target,),
    )
    target.write_text("partially applied")

    code = cli.main([
        "recover",
        "--case-root", str(case_root),
        "--output-dir", str(output_dir),
        "--transaction-id", transaction["transaction_id"],
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["restored_targets"] == ["config"]
    assert target.read_text() == "baseline"


def test_every_transaction_mutation_requires_both_owned_leases(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    kwargs = dict(
        output_dir=output_dir, step_id="solve", overrides=[], hypothesis="test",
        target_paths=(case_root / "config",),
    )
    with pytest.raises(RemediationTransactionError, match="owned case and output"):
        begin_remediation_transaction(case_root, **kwargs)
    with acquire_case_lease(case_root):
        with pytest.raises(RemediationTransactionError, match="owned case and output"):
            begin_remediation_transaction(case_root, **kwargs)
        with acquire_attempt_lease(tmp_path / "wrong-output"):
            with pytest.raises(RemediationTransactionError, match="owned case and output"):
                begin_remediation_transaction(case_root, **kwargs)

    transaction = _begin(case_root, output_dir)
    with pytest.raises(RemediationTransactionError, match="owned case and output"):
        finish_remediation_transaction(case_root, transaction, status="validated")
    with _owned(case_root, output_dir):
        validated = finish_remediation_transaction(
            case_root, transaction, status="validated",
        )
    with pytest.raises(RemediationTransactionError, match="owned case and output"):
        mark_remediation_dispatching(case_root, validated)
    with _owned(case_root, output_dir):
        dispatching = mark_remediation_dispatching(case_root, validated)
    with pytest.raises(RemediationTransactionError, match="owned case and output"):
        record_remediation_outcome(
            case_root, dispatching, execution_status="ok", attempt=1,
        )


def test_relative_lease_paths_match_canonical_transaction_identity(
    monkeypatch, tmp_path: Path,
) -> None:
    (tmp_path / "case").mkdir()
    monkeypatch.chdir(tmp_path)
    with acquire_case_lease(Path("case")):
        with acquire_attempt_lease(Path("output")):
            from omnidriver.core.runtime.attempt_lease import (
                attempt_lease_is_held, case_lease_is_held,
            )

            assert case_lease_is_held(Path("case"))
            assert attempt_lease_is_held(Path("output"))
            transaction = begin_remediation_transaction(
                Path("case"), output_dir=Path("output"), step_id="solve",
                overrides=[], hypothesis="relative paths", target_paths=(Path("config"),),
            )

    assert transaction["status"] == "applying"


def test_stale_transaction_cannot_overwrite_newer_case_head(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    first = _begin(case_root, output_dir)
    _finish(case_root, first, status="rejected", error="first rejected")
    second = _begin(case_root, output_dir, value="3")

    with _owned(case_root, output_dir):
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            finish_remediation_transaction(case_root, first, status="validated")

    assert read_remediation_transaction(case_root)["transaction_id"] == second["transaction_id"]


def test_duplicate_transition_is_rejected_by_revision_and_status(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    transaction = _begin(case_root, output_dir)
    with _owned(case_root, output_dir):
        validated = finish_remediation_transaction(
            case_root, transaction, status="validated",
        )
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            finish_remediation_transaction(case_root, transaction, status="validated")
        dispatching = mark_remediation_dispatching(case_root, validated)
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            mark_remediation_dispatching(case_root, validated)
        accepted = record_remediation_outcome(
            case_root, dispatching, execution_status="ok", attempt=1,
        )
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            record_remediation_outcome(
                case_root, dispatching, execution_status="ok", attempt=1,
            )

    assert [transaction["revision"], validated["revision"], dispatching["revision"], accepted["revision"]] == [1, 2, 3, 4]
    assert accepted["status"] == "accepted"


def test_expected_prior_status_is_part_of_compare_and_swap(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    transaction = _begin(case_root, output_dir)
    forged_expected = {**transaction, "status": "validated"}

    with _owned(case_root, output_dir):
        with pytest.raises(RemediationTransactionError, match="compare-and-swap"):
            finish_remediation_transaction(
                case_root, forged_expected, status="validated",
            )

    assert read_remediation_transaction(case_root)["status"] == "applying"


@pytest.mark.parametrize("incomplete_status", ["validated", "dispatching"])
def test_validated_or_dispatching_candidate_blocks_reuse_and_can_recover(
    tmp_path: Path, incomplete_status: str,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = _begin_targets(
        case_root, output_dir, step_id="solve", overrides=[], hypothesis="candidate",
        target_paths=(target,),
    )
    target.write_text("candidate")
    with _owned(case_root, output_dir):
        transaction = finish_remediation_transaction(
            case_root, transaction, status="validated",
        )
        if incomplete_status == "dispatching":
            transaction = mark_remediation_dispatching(case_root, transaction)

    with pytest.raises(RemediationTransactionError, match="interrupted"):
        require_reusable_case(case_root, explicit_repair=True)
    with _owned(case_root, output_dir):
        restored = restore_remediation_transaction(
            case_root, output_dir=output_dir,
            transaction_id=transaction["transaction_id"],
            expected_revision=transaction["revision"],
            expected_status=transaction["status"],
        )

    assert restored["status"] == "rolled_back"
    assert target.read_text() == "baseline"


def test_failed_execution_rejects_candidate_instead_of_accepting_it(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    transaction = _begin(case_root, output_dir)
    with _owned(case_root, output_dir):
        validated = finish_remediation_transaction(
            case_root, transaction, status="validated",
        )
        assert validated["status"] == "validated"
        dispatching = mark_remediation_dispatching(case_root, validated)
        rejected = record_remediation_outcome(
            case_root, dispatching, execution_status="failed", attempt=7,
        )

    assert rejected["status"] == "rejected"
    with pytest.raises(RemediationTransactionError, match="rejected"):
        require_reusable_case(case_root, explicit_repair=False)
