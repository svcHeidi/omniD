"""Crash/rejection semantics for case-local remediation journals."""
from __future__ import annotations

import json
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
    read_remediation_transaction,
    record_remediation_outcome,
    require_reusable_case,
    restore_remediation_transaction,
)


def _begin(case_root: Path, output_dir: Path, *, value: str = "2") -> dict:
    target = case_root / "system" / "controlDict"
    return begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
        step_id="solve",
        overrides=[{"driver_path": "value", "value": value}],
        hypothesis="smaller step improves stability",
        target_paths=(target,),
    )


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
    rejected = finish_remediation_transaction(
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
    accepted = finish_remediation_transaction(case_root, first, status="accepted")
    record_remediation_outcome(
        case_root, accepted, execution_status="failed", attempt=3,
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
    finish_remediation_transaction(
        case_root, first, status="rejected", error="invalid plan",
    )
    second = _begin(case_root, output_dir, value="3")
    finish_remediation_transaction(
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
    finish_remediation_transaction(
        case_root,
        first,
        status="accepted",
        effective_resolution=({"inspected_files": [str(external)]},),
    )
    second = _begin(case_root, output_dir, value="3")
    finish_remediation_transaction(
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
    transaction = begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
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
    transaction = begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
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
                restore_remediation_transaction(case_root, output_dir=output_dir)

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
    transaction = begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
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
                restore_remediation_transaction(case_root, output_dir=output_dir)

    assert target.read_text() == "candidate"


def test_recover_cli_restores_without_loading_a_plugin_or_dispatching(
    capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline")
    output_dir = tmp_path / "output"
    transaction = begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
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
