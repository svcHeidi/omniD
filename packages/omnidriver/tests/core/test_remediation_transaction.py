"""Crash/rejection semantics for case-local remediation journals."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.runtime.remediation_transaction import (
    MARKER_NAME,
    RemediationTransactionError,
    accepted_external_dependencies,
    begin_remediation_transaction,
    finish_remediation_transaction,
    read_remediation_transaction,
    record_remediation_outcome,
    require_reusable_case,
)


def _begin(case_root: Path, output_dir: Path, *, value: str = "2") -> dict:
    return begin_remediation_transaction(
        case_root,
        output_dir=output_dir,
        step_id="solve",
        overrides=[{"driver_path": "value", "value": value}],
        hypothesis="smaller step improves stability",
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
