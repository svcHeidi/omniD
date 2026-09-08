"""Bounded orchestration for evidence-driven repair experiments.

This layer is intentionally independent of workflow retry. A retry repeats one
execution policy; a repair experiment must bind a new hypothesis and proposal
to the failure evidence that motivated it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


CONTROL_DIR = ".omnidriver-repair-control"
LEGACY_JOURNAL_DIR = "repair_loops"
RESERVATION_DIR = "repair_reservations"


@dataclass(frozen=True)
class RepairBudgets:
    max_candidate_executions: int
    max_elapsed_seconds: float | None = None
    max_unchanged_failures: int = 2

    def __post_init__(self) -> None:
        if self.max_candidate_executions < 1:
            raise ValueError("max_candidate_executions must be positive")
        if self.max_elapsed_seconds is not None and self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive when supplied")
        if self.max_unchanged_failures < 1:
            raise ValueError("max_unchanged_failures must be positive")


@dataclass(frozen=True, init=False)
class RepairObservation:
    _canonical_json: str = field(repr=False)

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_canonical_json", _canonical_json(dict(evidence)))

    @property
    def evidence(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def digest(self) -> str:
        return _digest_json(self._canonical_json)


@dataclass(frozen=True, init=False)
class RepairProposal:
    hypothesis: str
    based_on_observation_digest: str
    _overrides_json: str = field(repr=False)

    def __init__(
        self,
        hypothesis: str,
        overrides: tuple[Mapping[str, Any], ...],
        based_on_observation_digest: str,
    ) -> None:
        object.__setattr__(self, "hypothesis", hypothesis)
        object.__setattr__(self, "based_on_observation_digest", based_on_observation_digest)
        object.__setattr__(
            self, "_overrides_json", _canonical_json([dict(item) for item in overrides]),
        )

    @property
    def overrides(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(self._overrides_json))

    @property
    def digest(self) -> str:
        return _digest({"hypothesis": self.hypothesis, "overrides": self.overrides})


@dataclass(frozen=True)
class RepairReservation:
    loop_id: str
    execution: int
    reservation_id: str
    observation_digest: str
    proposal_digest: str

    def __post_init__(self) -> None:
        for name in ("loop_id", "reservation_id"):
            value = getattr(self, name)
            try:
                canonical = str(uuid.UUID(value))
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"repair {name} must be a UUID") from exc
            if canonical != value:
                raise ValueError(f"repair {name} must use canonical UUID text")
        if (
            isinstance(self.execution, bool)
            or not isinstance(self.execution, int)
            or self.execution < 1
        ):
            raise ValueError("repair execution must be positive")
        for name in ("observation_digest", "proposal_digest"):
            value = getattr(self, name)
            if not _is_sha256_digest(value):
                raise ValueError(f"repair {name} must be a sha256 digest")


@dataclass(frozen=True)
class RepairExperimentResult:
    status: str
    observation: RepairObservation
    loop_id: str
    execution: int
    reservation_id: str
    observation_digest: str
    proposal_digest: str
    transaction_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "failed", "rejected"}:
            raise ValueError(f"invalid repair experiment status: {self.status}")


@dataclass(frozen=True)
class RepairLoopOutcome:
    status: str
    reason: str
    executions: int
    unchanged_failures: int
    observation: RepairObservation
    journal_path: Path


def run_repair_loop(
    initial_observation: RepairObservation,
    *,
    output_dir: Path,
    budgets: RepairBudgets,
    propose: Callable[[RepairObservation], RepairProposal | None],
    execute_candidate: Callable[
        [RepairProposal, RepairReservation], RepairExperimentResult
    ],
    monotonic: Callable[[], float] = time.monotonic,
    loop_id: str | None = None,
) -> RepairLoopOutcome:
    """Run bounded reason/change/compare cycles and durably record each one.

    ``propose`` runs outside execution ownership. ``execute_candidate`` owns the
    full mutation -> effective resolution -> replan -> dispatch transaction and
    must acquire its case/output leases. A reservation is persisted before that
    callback, so a crash cannot silently reuse an execution budget slot.
    """
    loop_id = _validated_loop_id(loop_id or str(uuid.uuid4()))
    control_dir = _control_dir(Path(output_dir))
    lock_path = control_dir / f"{loop_id}.lock"
    with _acquire_loop_lock(lock_path):
        return _run_repair_loop_locked(
            initial_observation,
            output_dir=output_dir,
            budgets=budgets,
            propose=propose,
            execute_candidate=execute_candidate,
            monotonic=monotonic,
            loop_id=loop_id,
        )


def _run_repair_loop_locked(
    initial_observation: RepairObservation,
    *,
    output_dir: Path,
    budgets: RepairBudgets,
    propose: Callable[[RepairObservation], RepairProposal | None],
    execute_candidate: Callable[
        [RepairProposal, RepairReservation], RepairExperimentResult
    ],
    monotonic: Callable[[], float],
    loop_id: str,
) -> RepairLoopOutcome:
    path = _control_dir(Path(output_dir)) / f"{loop_id}.json"
    legacy_path = Path(output_dir) / LEGACY_JOURNAL_DIR / f"{loop_id}.json"
    if not path.exists() and legacy_path.exists():
        _atomic_write(path, _load_journal(legacy_path))
    started = monotonic()
    observation = initial_observation
    executions = 0
    unchanged = 0
    if path.exists():
        journal = _load_journal(path)
        if journal.get("budgets") != asdict(budgets):
            raise ValueError("repair-loop budgets do not match the existing loop")
        if journal.get("initial_observation_digest") != initial_observation.digest:
            raise ValueError("initial observation does not match the existing repair loop")
        experiments = journal.get("experiments")
        if not isinstance(experiments, list):
            raise ValueError("existing repair-loop journal is malformed")
        executions = len(experiments)
        if journal.get("status") != "running":
            final = RepairObservation(journal.get("final_observation", {}))
            return RepairLoopOutcome(
                str(journal["status"]), str(journal["reason"]), executions,
                int(journal.get("unchanged_failures", 0)), final, path,
            )
        if experiments and experiments[-1].get("status") == "reserved":
            recovered = _recover_reserved_result(
                Path(output_dir), experiments[-1], loop_id,
            )
            if recovered is None:
                experiments[-1].update(status="interrupted", finished_at=_now())
                return _finish(
                    path, journal, "failed", "interrupted_candidate_requires_recovery",
                    executions, 0, initial_observation,
                )
            experiments[-1].update(
                status=recovered.status,
                finished_at=_now(),
                resulting_observation_digest=recovered.observation.digest,
                resulting_observation=recovered.observation.evidence,
                transaction_id=recovered.transaction_id,
                recovered_from_reservation=True,
            )
            _atomic_write(path, journal)
            if recovered.status == "succeeded":
                return _finish(
                    path, journal, "succeeded", "candidate_succeeded",
                    executions, 0, recovered.observation,
                )
        if experiments:
            observation = RepairObservation(experiments[-1]["resulting_observation"])
            unchanged = _trailing_unchanged_failures(experiments)
        return _continue_loop(
            path, journal, observation, executions, unchanged, started,
            budgets, propose, execute_candidate, monotonic,
        )
    journal: dict[str, Any] = {
        "schema_version": 1,
        "loop_id": loop_id,
        "status": "running",
        "started_at": _now(),
        "budgets": asdict(budgets),
        "initial_observation_digest": observation.digest,
        "initial_observation": observation.evidence,
        "experiments": [],
    }
    _atomic_write(path, journal)

    return _continue_loop(
        path, journal, observation, executions, unchanged, started,
        budgets, propose, execute_candidate, monotonic,
    )


def _continue_loop(
    path: Path,
    journal: dict[str, Any],
    observation: RepairObservation,
    executions: int,
    unchanged: int,
    started: float,
    budgets: RepairBudgets,
    propose: Callable[[RepairObservation], RepairProposal | None],
    execute_candidate: Callable[
        [RepairProposal, RepairReservation], RepairExperimentResult
    ],
    monotonic: Callable[[], float],
) -> RepairLoopOutcome:

    while True:
        elapsed = monotonic() - started
        if executions >= budgets.max_candidate_executions:
            return _finish(path, journal, "stopped", "execution_budget_exhausted",
                           executions, unchanged, observation)
        if budgets.max_elapsed_seconds is not None and elapsed >= budgets.max_elapsed_seconds:
            return _finish(path, journal, "stopped", "elapsed_budget_exhausted",
                           executions, unchanged, observation)

        try:
            proposal = propose(observation)
        except Exception as exc:
            _finish(path, journal, "failed", "proposer_error",
                    executions, unchanged, observation)
            raise
        if proposal is None:
            return _finish(path, journal, "stopped", "proposer_stopped",
                           executions, unchanged, observation)
        if not proposal.hypothesis.strip():
            _finish(path, journal, "failed", "proposer_contract_error",
                    executions, unchanged, observation)
            raise ValueError("repair hypothesis must not be empty")
        if proposal.based_on_observation_digest != observation.digest:
            _finish(path, journal, "failed", "proposer_contract_error",
                    executions, unchanged, observation)
            raise ValueError("repair proposal is based on stale observation evidence")
        if (
            budgets.max_elapsed_seconds is not None
            and monotonic() - started >= budgets.max_elapsed_seconds
        ):
            return _finish(path, journal, "stopped", "elapsed_budget_exhausted",
                           executions, unchanged, observation)

        executions += 1
        reservation = RepairReservation(
            loop_id=str(journal["loop_id"]),
            execution=executions,
            reservation_id=str(uuid.uuid4()),
            observation_digest=observation.digest,
            proposal_digest=proposal.digest,
        )
        experiment = {
            "execution": executions,
            "reservation_id": reservation.reservation_id,
            "status": "reserved",
            "reserved_at": _now(),
            "observation_digest": reservation.observation_digest,
            "observation": observation.evidence,
            "hypothesis": proposal.hypothesis,
            "overrides": [dict(item) for item in proposal.overrides],
            "proposal_digest": reservation.proposal_digest,
        }
        journal["experiments"].append(experiment)
        _atomic_write(path, journal)

        try:
            result = execute_candidate(proposal, reservation)
        except Exception as exc:
            experiment.update(status="error", finished_at=_now(), error=str(exc))
            return _finish(path, journal, "failed", "candidate_executor_error",
                           executions, unchanged, observation)

        mismatches = _result_binding_mismatches(result, reservation)
        if mismatches:
            message = (
                "repair candidate result binding does not match reservation: "
                + ", ".join(mismatches)
            )
            experiment.update(status="error", finished_at=_now(), error=message)
            _finish(path, journal, "failed", "candidate_result_contract_error",
                    executions, unchanged, observation)
            raise ValueError(message)

        next_observation = result.observation
        experiment.update(
            status=result.status,
            finished_at=_now(),
            resulting_observation_digest=next_observation.digest,
            resulting_observation=next_observation.evidence,
            transaction_id=result.transaction_id,
        )
        _atomic_write(path, journal)
        if result.status == "succeeded":
            return _finish(path, journal, "succeeded", "candidate_succeeded",
                           executions, unchanged, next_observation)
        unchanged = unchanged + 1 if next_observation.digest == observation.digest else 0
        observation = next_observation
        if unchanged >= budgets.max_unchanged_failures:
            return _finish(path, journal, "stopped", "repeated_unchanged_failure",
                           executions, unchanged, observation)


def _result_binding_mismatches(
    result: RepairExperimentResult,
    reservation: RepairReservation,
) -> tuple[str, ...]:
    if not isinstance(result, RepairExperimentResult):
        return ("result_type",)
    expected = {
        "loop_id": reservation.loop_id,
        "execution": reservation.execution,
        "reservation_id": reservation.reservation_id,
        "observation_digest": reservation.observation_digest,
        "proposal_digest": reservation.proposal_digest,
    }
    return tuple(
        field_name
        for field_name, expected_value in expected.items()
        if getattr(result, field_name) != expected_value
    )


def _recover_reserved_result(
    output_dir: Path,
    experiment: Mapping[str, Any],
    loop_id: str,
) -> RepairExperimentResult | None:
    try:
        reservation = RepairReservation(
            loop_id=loop_id,
            execution=int(experiment["execution"]),
            reservation_id=str(experiment["reservation_id"]),
            observation_digest=str(experiment["observation_digest"]),
            proposal_digest=str(experiment["proposal_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("reserved repair experiment binding is malformed") from exc
    claim_path = _reservation_path(output_dir, loop_id, reservation.execution)
    if not claim_path.exists():
        return None
    claim = _load_reservation_claim(claim_path)
    if any(claim.get(name) != value for name, value in asdict(reservation).items()):
        raise ValueError("repair reservation claim does not match the loop journal")
    if claim.get("status") == "transaction_committed":
        terminal = claim.get("terminal_transaction")
        if not isinstance(terminal, dict):
            raise ValueError("committed repair reservation omitted its transaction")
        from .attempt_lease import acquire_attempt_lease, acquire_case_lease
        from .remediation_transaction import reconcile_committed_repair_transaction

        case_root = claim.get("case_root")
        if not isinstance(case_root, str):
            raise ValueError("repair reservation claim omitted its case identity")
        with acquire_case_lease(Path(case_root)):
            with acquire_attempt_lease(output_dir):
                reconciled = reconcile_committed_repair_transaction(
                    Path(case_root), output_dir=output_dir, transaction=terminal,
                )
        recovered = _experiment_result_from_transaction(reconciled, reservation)
        if recovered is None:
            raise ValueError("committed repair witness is not terminal")
        complete_repair_reservation(
            output_dir, reservation, status=recovered.status,
            observation=recovered.observation,
            transaction_id=recovered.transaction_id,
        )
        return recovered
    if claim.get("status") == "claimed":
        recovered = _terminal_transaction_result(
            output_dir, reservation, case_root=claim.get("case_root"),
        )
        if recovered is None:
            return None
        complete_repair_reservation(
            output_dir,
            reservation,
            status=recovered.status,
            observation=recovered.observation,
            transaction_id=recovered.transaction_id,
        )
        return recovered
    if claim.get("status") != "terminal":
        raise ValueError("repair reservation claim has an invalid status")
    evidence = claim.get("resulting_observation")
    if not isinstance(evidence, dict):
        raise ValueError("terminal repair reservation omitted its observation")
    observation = RepairObservation(evidence)
    if observation.digest != claim.get("resulting_observation_digest"):
        raise ValueError("terminal repair reservation observation digest mismatch")
    return RepairExperimentResult(
        str(claim.get("result_status")),
        observation,
        **asdict(reservation),
        transaction_id=claim.get("transaction_id"),
    )


def _terminal_transaction_result(
    output_dir: Path,
    reservation: RepairReservation,
    *,
    case_root: object,
) -> RepairExperimentResult | None:
    if not isinstance(case_root, str):
        raise ValueError("repair reservation claim omitted its case identity")
    from .attempt_lease import acquire_attempt_lease, acquire_case_lease
    from .remediation_transaction import reconcile_terminal_remediation_record

    with acquire_case_lease(Path(case_root)):
        with acquire_attempt_lease(output_dir):
            head = reconcile_terminal_remediation_record(
                Path(case_root),
                output_dir=output_dir,
                repair_binding=asdict(reservation),
            )
    if head is not None:
        return _experiment_result_from_transaction(head, reservation)
    records = Path(output_dir).resolve() / "remediation_transactions"
    for path in sorted(records.glob("*.json")):
        try:
            transaction = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(transaction, dict):
            continue
        if transaction.get("repair_binding") != asdict(reservation):
            continue
        return _experiment_result_from_transaction(transaction, reservation)
    return None


def _experiment_result_from_transaction(
    transaction: Mapping[str, Any], reservation: RepairReservation,
) -> RepairExperimentResult | None:
    result = transaction.get("repair_result")
    if transaction.get("status") not in {"accepted", "rejected", "rolled_back"}:
        return None
    if not isinstance(result, dict) or not isinstance(result.get("observation"), dict):
        return None
    observation = RepairObservation(result["observation"])
    if observation.digest != result.get("observation_digest"):
        raise ValueError("terminal remediation observation digest mismatch")
    expected_transaction_statuses = {
        "succeeded": {"accepted"},
        "failed": {"rejected"},
        "rejected": {"rejected", "rolled_back"},
    }
    if transaction["status"] not in expected_transaction_statuses.get(
        result.get("status"), set(),
    ):
        raise ValueError("terminal remediation result status is inconsistent")
    return RepairExperimentResult(
        str(result.get("status")),
        observation,
        **asdict(reservation),
        transaction_id=str(transaction["transaction_id"]),
    )


def _validated_loop_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("repair loop_id must be a UUID") from exc
    if str(parsed) != value:
        raise ValueError("repair loop_id must use canonical UUID text")
    return value


def _control_dir(output_dir: Path) -> Path:
    output = output_dir.resolve()
    identity = hashlib.sha256(str(output).encode()).hexdigest()
    return output.parent / CONTROL_DIR / identity


def claim_repair_reservation(
    output_dir: Path, reservation: RepairReservation, *, case_root: Path,
) -> Path:
    """Durably consume a repair slot exactly once while output ownership is held."""
    path = _reservation_path(output_dir, reservation.loop_id, reservation.execution)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": "claimed",
        "claimed_at": _now(),
        "case_root": str(Path(case_root).resolve()),
        **asdict(reservation),
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            "repair reservation was already claimed or its execution slot was reused"
        ) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "posix":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return path


def complete_repair_reservation(
    output_dir: Path,
    reservation: RepairReservation,
    *,
    status: str,
    observation: RepairObservation,
    transaction_id: str | None,
) -> None:
    if status not in {"succeeded", "failed", "rejected"}:
        raise ValueError(f"invalid repair reservation result status: {status}")
    path = _reservation_path(output_dir, reservation.loop_id, reservation.execution)
    claim = _load_reservation_claim(path)
    if claim.get("status") not in {"claimed", "transaction_committed"} or any(
        claim.get(name) != value for name, value in asdict(reservation).items()
    ):
        raise RuntimeError("repair reservation completion does not match its claim")
    _atomic_write(path, {
        **claim,
        "status": "terminal",
        "finished_at": _now(),
        "result_status": status,
        "resulting_observation": observation.evidence,
        "resulting_observation_digest": observation.digest,
        "transaction_id": transaction_id,
    })


def commit_repair_transaction_witness(
    output_dir: Path, transaction: Mapping[str, Any],
) -> None:
    """Commit a bound terminal result before exposing a reusable case head."""
    binding = transaction.get("repair_binding")
    result = transaction.get("repair_result")
    if not isinstance(binding, dict) or not isinstance(result, dict):
        raise RuntimeError("terminal repair transaction omitted its durable binding")
    reservation = RepairReservation(**binding)
    path = _reservation_path(output_dir, reservation.loop_id, reservation.execution)
    claim = _load_reservation_claim(path)
    if claim.get("status") != "claimed" or any(
        claim.get(name) != value for name, value in binding.items()
    ):
        raise RuntimeError("terminal repair transaction does not match its claim")
    _atomic_write(path, {
        **claim,
        "status": "transaction_committed",
        "transaction_committed_at": _now(),
        "terminal_transaction": dict(transaction),
    })


def _reservation_path(output_dir: Path, loop_id: str, execution: int) -> Path:
    return _control_dir(Path(output_dir)) / RESERVATION_DIR / loop_id / f"{execution}.json"


def _load_reservation_claim(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"repair reservation claim is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError(f"repair reservation claim is malformed: {path}")
    return payload


@contextmanager
def _acquire_loop_lock(path: Path):
    if os.name != "posix":
        raise RuntimeError("repair-loop ownership requires POSIX advisory locking")
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"repair loop is already owned: {path.stem}") from exc
        yield
    finally:
        handle.close()


def _load_journal(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"repair-loop journal is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"repair-loop journal is malformed: {path}")
    return payload


def _trailing_unchanged_failures(experiments: list[dict[str, Any]]) -> int:
    count = 0
    for item in reversed(experiments):
        if (
            item.get("status") not in {"failed", "rejected"}
            or item.get("resulting_observation_digest") != item.get("observation_digest")
        ):
            break
        count += 1
    return count


def _finish(path: Path, journal: dict[str, Any], status: str, reason: str,
            executions: int, unchanged: int,
            observation: RepairObservation) -> RepairLoopOutcome:
    journal.update(status=status, reason=reason, finished_at=_now(),
                   executions=executions, unchanged_failures=unchanged,
                   final_observation_digest=observation.digest,
                   final_observation=observation.evidence)
    _atomic_write(path, journal)
    return RepairLoopOutcome(status, reason, executions, unchanged, observation, path)


def _digest(value: Any) -> str:
    return _digest_json(_canonical_json(value))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("repair evidence and overrides must be strict JSON values") from exc


def _digest_json(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(char in "0123456789abcdef" for char in suffix)


def observation_from_failure_context(
    failure_context: Mapping[str, Any],
) -> RepairObservation:
    """Remove per-attempt locations while retaining comparable failure evidence."""
    stable_keys = (
        "step_id", "exit_code", "diagnostics", "stdout_tail", "stderr_tail",
        "stdout_truncated", "stderr_truncated",
    )
    return RepairObservation({
        key: failure_context[key] for key in stable_keys if key in failure_context
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
